import secrets
import threading
from dataclasses import replace

import pytest

from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.cards import DECK, Rank
from skat.engine.deal import Position, positions_from
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.engine.ramsch import (
    DurchmarschRule,
    JungfrauRule,
    RamschOptions,
    RamschPlaying,
    RamschScoring,
    play_ramsch_card,
)
from skat.engine.schieberamsch import PushingRule
from skat.store.migrate import create_store_engine, migrate
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.hand_state import game_of, pushing_of
from skat.table.playing import PlayCardCommand
from skat.table.pushing import PushingCommand, PushingKind
from skat.table.records import RamschOccasion, RamschSetting, RuleSetId, TableId, TableOptions
from skat.table.rule_sets import RuleSet
from skat.table.service import TableService
from tests.support.migrations import upgrade_to
from tests.support.rule_set_rows import a_set, row_count, save, sets_of
from tests.support.stored_game import nobody_connected, person, seated_table_id

pytestmark = pytest.mark.postgres


@pytest.fixture
def set_name():
    return "Felix"


@pytest.fixture
def felix_without_pushing():
    """The operator's set as it stands before the pushing revision."""
    return TableOptions(
        show_running_points=False,
        kontra=KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD),
        bock=BockOptions(
            frozenset(
                {BockTrigger.SIXTY_SIXTY, BockTrigger.WON_GRAND_HAND, BockTrigger.LOST_AFTER_KONTRA, BockTrigger.RE}
            ),
            BockOverlap.APPEND,
        ),
        ramsch=RamschSetting(
            RamschOccasion.PASSED_IN,
            RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120),
        ),
    )


@pytest.fixture
def felix_options(felix_without_pushing):
    ramsch = felix_without_pushing.ramsch
    return replace(felix_without_pushing, ramsch=replace(ramsch, pushing=PushingRule.JACKS_STAY))


@pytest.fixture
def before_the_pushing_value(unmigrated_engine):
    upgrade_to(unmigrated_engine, "0031")
    return unmigrated_engine


def test_a_migration_without_the_operator_account_leaves_an_existing_felix_and_does_not_fail(
    before_the_pushing_value, operator_account_id, set_name, felix_without_pushing
):
    earlier = a_set(operator_account_id, set_name, felix_without_pushing)
    save(before_the_pushing_value, earlier)

    migrate(before_the_pushing_value, operator_account_id=None)

    assert sets_of(before_the_pushing_value, operator_account_id) == (earlier,)


def test_the_operator_account_gets_felix_with_the_pushing_rule_and_the_earlier_values(
    before_the_pushing_value, operator_account_id, set_name, felix_options
):
    migrate(before_the_pushing_value, operator_account_id=operator_account_id)

    [felix] = sets_of(before_the_pushing_value, operator_account_id)
    assert (felix.name, felix.options) == (set_name, felix_options)
    assert RuleSetId.parse(felix.id.value) == felix.id


def test_a_fresh_database_taken_to_head_holds_one_felix_with_the_pushing_rule(
    unmigrated_engine, operator_account_id, set_name, felix_options
):
    migrate(unmigrated_engine, operator_account_id=operator_account_id)

    [felix] = sets_of(unmigrated_engine, operator_account_id)
    assert (felix.name, felix.options) == (set_name, felix_options)
    assert row_count(unmigrated_engine) == 1


def test_the_felix_without_pushing_is_replaced_keeping_its_id(
    before_the_pushing_value, operator_account_id, set_name, felix_without_pushing, felix_options
):
    earlier = a_set(operator_account_id, set_name, felix_without_pushing)
    save(before_the_pushing_value, earlier)

    migrate(before_the_pushing_value, operator_account_id=operator_account_id)

    replaced = RuleSet(earlier.id, operator_account_id, set_name, felix_options)
    assert sets_of(before_the_pushing_value, operator_account_id) == (replaced,)


def test_another_name_of_the_account_and_another_accounts_felix_stay_untouched(
    before_the_pushing_value, operator_account_id, set_name
):
    other_name = a_set(operator_account_id, "Abend")
    others_felix = a_set(f"account-{secrets.token_hex(8)}", set_name)
    save(before_the_pushing_value, other_name)
    save(before_the_pushing_value, others_felix)

    migrate(before_the_pushing_value, operator_account_id=operator_account_id)

    assert sets_of(before_the_pushing_value, others_felix.owner_account) == (others_felix,)
    by_name = {rule_set.name: rule_set for rule_set in sets_of(before_the_pushing_value, operator_account_id)}
    assert by_name["Abend"] == other_name
    assert row_count(before_the_pushing_value) == 3


@pytest.fixture
def a_second_engine(unmigrated_database_url):
    engine = create_store_engine(unmigrated_database_url)
    yield engine
    engine.dispose()


def test_two_migrations_at_once_leave_one_felix(
    before_the_pushing_value, a_second_engine, operator_account_id, set_name, felix_options
):
    failures: list[BaseException] = []
    start = threading.Barrier(2)

    def run(engine):
        start.wait()
        try:
            migrate(engine, operator_account_id=operator_account_id)
        except BaseException as failure:
            failures.append(failure)

    threads = [threading.Thread(target=run, args=(engine,)) for engine in (before_the_pushing_value, a_second_engine)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    [felix] = sets_of(before_the_pushing_value, operator_account_id)
    assert (felix.name, felix.options) == (set_name, felix_options)
    assert row_count(before_the_pushing_value) == 1


class TestARamschPlayedWithTheMigratedSet:
    @pytest.fixture
    def table(self, before_the_pushing_value, operator_account_id):
        migrate(before_the_pushing_value, operator_account_id=operator_account_id)
        [felix] = sets_of(before_the_pushing_value, operator_account_id)
        return StagedTable(before_the_pushing_value, felix.options)

    def test_a_table_opened_with_the_sets_options_answers_them_and_takes_the_stage_of_pushing(
        self, table, felix_options
    ):
        table.pass_all()

        result = table.step(Position.FOREHAND, PushingKind.TAKE)

        assert table.record.options == felix_options
        assert result.refusal is None

    def test_two_pushes_double_twice_and_a_pending_bock_game_doubles_the_list_score_again(self, table):
        table.hold_pending_bock_games(2)
        table.pass_all()
        table.step(Position.FOREHAND, PushingKind.TAKE)
        table.step(Position.FOREHAND, PushingKind.PUT_BACK, table.two_cards_to_put_back(Position.FOREHAND))
        table.step(Position.MIDDLEHAND, PushingKind.PUSH)
        table.step(Position.REARHAND, PushingKind.PUSH)

        table.play_out()

        result = table.result()
        assert (result.pushes, result.push_factor, result.bock_factor) == (2, 4, 2)
        # Points scoring gives the loser minus the points, doubled for a Jungfrau; both factors multiply that.
        base = 2 if result.jungfrau else 1
        factor = base * result.push_factor * result.bock_factor
        assert [seat.score for seat in result.seats] == [
            -seat.points * factor if seat.score else 0 for seat in result.seats
        ]
        assert any(seat.score for seat in result.seats)


class StagedTable:
    """A table opened with the given options, seated, from where a test passes the auction and plays the Ramsch."""

    def __init__(self, engine, options):
        self.transactions = PostgresTableTransactions(engine)
        self.service = TableService(self.transactions)
        self.table_id = seated_table_id(self.service, options)
        by_seat = {1: person("Anna"), 2: person("Ben"), 3: person("Cleo")}
        self.actors = {position: by_seat[seat] for seat, position in positions_from(self.record.dealer).items()}
        self._commands = 0

    @property
    def record(self):
        with self.transactions.begin() as transaction:
            return transaction.table(TableId(self.table_id))

    def hold_pending_bock_games(self, *rounds):
        with self.transactions.begin() as transaction:
            transaction.save_table(
                replace(transaction.locked_table(TableId(self.table_id)), bock=BockRounds(rounds)), played_at=None
            )

    def pass_all(self):
        for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND):
            command = AuctionCommand(
                f"pass-{position.value}", self.table_id, self.record.version, AuctionAction.PASS, None
            )
            self.service.take_auction_step(self.actors[position], command, nobody_connected())

    def step(self, position, kind, cards=()):
        self._commands += 1
        command = PushingCommand(f"step-{self._commands}", self.table_id, self.record.version, kind, tuple(cards))
        return self.service.take_pushing_step(self.actors[position], command, nobody_connected())

    def two_cards_to_put_back(self, position):
        hand = pushing_of(self.record).deal.hands[position]
        return tuple(card for card in hand if card.rank is not Rank.JACK)[:2]

    def play_out(self):
        while isinstance(state := game_of(self.record), RamschPlaying):
            card = next(
                each
                for each in DECK
                if each in state.hands[state.turn] and play_ramsch_card(state, state.turn, each).refusal is None
            )
            command = PlayCardCommand(
                f"card-{len(self.record.progress.plays)}", self.table_id, self.record.version, card
            )
            assert self.service.play_card(self.actors[state.turn], command, nobody_connected()).refusal is None

    def result(self):
        return self.service.view(self.actors[Position.FOREHAND], self.table_id, frozenset()).result
