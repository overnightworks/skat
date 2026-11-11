import pytest
from sqlalchemy import text

from skat.engine.cards import DECK, Rank
from skat.engine.deal import Position, positions_from
from skat.engine.ramsch import (
    DurchmarschRule,
    JungfrauRule,
    RamschOptions,
    RamschPlaying,
    RamschScoring,
    play_ramsch_card,
)
from skat.engine.schieberamsch import PushingRule, PushRefusal
from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.hand_state import game_of, pushing_of
from skat.table.playing import PlayCardCommand
from skat.table.pushing import PushingCommand, PushingKind
from skat.table.records import RamschOccasion, RamschSetting, TableOptions
from skat.table.service import TableService
from tests.support.stored_game import count_rows, nobody_connected, person, seated_table_id

pytestmark = pytest.mark.postgres

OPTIONS = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120),
        PushingRule.JACKS_STAY,
    )
)
FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


class StageTable:
    """A table whose Ramsch has pushing and where all three passed, so its stage runs."""

    def __init__(self, service, transactions, stored):
        self.service = service
        self.transactions = transactions
        self.stored = stored
        self.table_id = seated_table_id(service, OPTIONS)
        by_seat = {1: person("Anna"), 2: person("Ben"), 3: person("Cleo")}
        self.actors = {position: by_seat[seat] for seat, position in positions_from(self.record.dealer).items()}
        for position in (MIDDLEHAND, REARHAND, FOREHAND):
            command = AuctionCommand(
                f"pass-{position.value}", self.table_id, self.record.version, AuctionAction.PASS, None
            )
            service.take_auction_step(self.actors[position], command, nobody_connected())
        self._commands = 0

    @property
    def record(self):
        return self.stored(self.transactions, self.table_id)

    def step(self, position, kind, cards=(), *, command_id=None, service=None):
        self._commands += 1
        command = PushingCommand(
            command_id or f"step-{self._commands}", self.table_id, self.record.version, kind, tuple(cards)
        )
        return (service or self.service).take_pushing_step(self.actors[position], command, nobody_connected())

    def two_cards_to_put_back(self, position):
        hand = pushing_of(self.record).deal.hands[position]
        return tuple(card for card in hand if card.rank is not Rank.JACK)[:2]

    def take_and_put_back(self, position):
        assert self.step(position, PushingKind.TAKE).refusal is None
        assert self.step(position, PushingKind.PUT_BACK, self.two_cards_to_put_back(position)).refusal is None

    def play(self, number):
        for _ in range(number):
            state = game_of(self.record)
            assert isinstance(state, RamschPlaying)
            card = next(
                each
                for each in DECK
                if each in state.hands[state.turn] and play_ramsch_card(state, state.turn, each).refusal is None
            )
            command = PlayCardCommand(
                f"card-{len(self.record.progress.plays)}", self.table_id, self.record.version, card
            )
            assert self.service.play_card(self.actors[state.turn], command, nobody_connected()).refusal is None

    def views(self, service=None):
        return [
            (service or self.service).view(self.actors[position], self.table_id, frozenset()).hand
            for position in (FOREHAND, MIDDLEHAND, REARHAND)
        ]


def restarted(database_url):
    engine = create_store_engine(database_url)
    return engine, TableService(PostgresTableTransactions(engine))


def a_take(table):
    table.step(FOREHAND, PushingKind.TAKE)


def a_put_back(table):
    a_take(table)
    table.step(FOREHAND, PushingKind.PUT_BACK, table.two_cards_to_put_back(FOREHAND))


def two_pushes(table):
    table.take_and_put_back(FOREHAND)
    table.step(MIDDLEHAND, PushingKind.PUSH)
    table.step(REARHAND, PushingKind.PUSH)


def a_ramsch_underway(table):
    two_pushes(table)
    table.play(5)


@pytest.mark.parametrize(
    "reach_the_stage",
    [
        pytest.param(lambda table: None, id="before-any-step"),
        pytest.param(a_take, id="after-a-take"),
        pytest.param(a_put_back, id="after-a-put-back"),
        pytest.param(two_pushes, id="after-the-stage"),
        pytest.param(a_ramsch_underway, id="mid-ramsch"),
    ],
)
def test_every_seat_reads_the_same_hand_after_a_restart_and_the_stage_goes_on(
    service, transactions, stored, database_url, reach_the_stage
):
    table = StageTable(service, transactions, stored)
    reach_the_stage(table)
    before = table.views()
    engine, again = restarted(database_url)
    try:
        after = table.views(again)
        stored_steps = count_rows(engine, "pushing_steps")
    finally:
        engine.dispose()

    assert after == before
    assert stored_steps == len(table.record.progress.pushing)


def test_the_stage_continues_on_a_restarted_service(service, transactions, stored, database_url):
    table = StageTable(service, transactions, stored)
    a_take(table)
    engine, again = restarted(database_url)
    try:
        put = table.step(FOREHAND, PushingKind.PUT_BACK, table.two_cards_to_put_back(FOREHAND), service=again)
    finally:
        engine.dispose()

    assert put.refusal is None
    assert pushing_of(table.record).turn is MIDDLEHAND


def test_a_refused_put_back_keeps_its_refusal_across_a_restart_and_stores_no_step(
    service, transactions, stored, database_url
):
    table = StageTable(service, transactions, stored)
    a_take(table)
    jack = next(card for card in pushing_of(table.record).deal.hands[FOREHAND] if card.rank is Rank.JACK)
    other = next(card for card in pushing_of(table.record).deal.hands[FOREHAND] if card != jack)
    first = table.step(FOREHAND, PushingKind.PUT_BACK, (jack, other), command_id="put-back-1")
    engine, again = restarted(database_url)
    try:
        replayed = table.step(FOREHAND, PushingKind.PUT_BACK, (jack, other), command_id="put-back-1", service=again)
    finally:
        engine.dispose()

    assert (first.refusal, replayed.refusal) == (PushRefusal.JACK_PUT_BACK, PushRefusal.JACK_PUT_BACK)
    assert len(table.record.progress.pushing) == 1


def test_the_last_card_stores_the_pushes_and_forgets_the_log_and_the_entry_survives_a_restart(
    service, transactions, stored, database_url
):
    table = StageTable(service, transactions, stored)
    two_pushes(table)
    table.play(30)
    engine, again = restarted(database_url)
    try:
        view = again.view(table.actors[FOREHAND], table.table_id, frozenset())
        with engine.connect() as connection:
            row = connection.execute(text("SELECT kind, pushes FROM game_list")).one()
        steps = count_rows(engine, "pushing_steps")
    finally:
        engine.dispose()

    assert (tuple(row), steps) == (("ramsch", 2), 0)
    assert (view.hand, view.result.pushes, view.result.push_factor) == (None, 2, 4)


def test_a_stored_log_the_engine_refuses_raises_at_the_next_command(service, transactions, stored, database_url):
    table = StageTable(service, transactions, stored)
    engine = create_store_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO pushing_steps VALUES (:id, 1, 'rearhand', 'push', NULL, NULL, NULL, NULL)"),
                {"id": table.table_id},
            )
    finally:
        engine.dispose()

    with pytest.raises(ValueError, match="impossible pushing log"):
        table.step(FOREHAND, PushingKind.TAKE)
