import itertools
import random
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, table, text

from skat.engine.bidding import Bid
from skat.engine.cards import DECK
from skat.engine.deal import SEATS, Position, next_dealer, positions_from
from skat.store.migrate import create_store_engine
from skat.store.tables import DealtHandRewrittenError, PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.ready import ReadyCommand
from skat.table.records import (
    Actor,
    CloseTable,
    CreateTable,
    HandProgress,
    Refusal,
    SeatHeld,
    SitDown,
    StandUp,
    TableId,
    TableOptions,
    Visibility,
)
from skat.table.service import CommandIdReusedError, TableService
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS
from skat.web.tables import TABLES_PATH
from tests.support.faulty_tables import BothReadBeforeEitherWrites, FaultyTableTransactions
from tests.support.played_game import after_the_first_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FakeTime, Skat, streams_of

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
THIRD_PLAYER = Actor(account_id="account-third", display_name="Cleo")


@pytest.fixture
def engine(database_url):
    engine = create_store_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def service(engine):
    return TableService(PostgresTableTransactions(engine))


def count(engine, table_name):
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table(table_name))).scalar_one()


def test_a_created_table_reads_back_the_same_after_a_reload(service):
    created = service.create(OPENER, CreateTable(command_id="command-1"))

    assert service.view(OPENER, created.id, frozenset()) == created
    assert [(chair.seat, chair.occupant_name) for chair in created.chairs] == [(1, "Anna"), (2, None), (3, None)]


def test_a_table_opened_with_the_switch_on_reads_it_back_after_a_reload(service):
    created = service.create(
        OPENER, CreateTable(command_id="command-1", options=TableOptions(show_running_points=True))
    )

    assert created.options == TableOptions(show_running_points=True)
    assert service.view(OPENER, created.id, frozenset()).options == created.options


def test_a_table_stored_without_a_switch_reads_it_off(service, engine):
    old_id = "a" * 32
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES (:id, 1)"), {"id": old_id})
        connection.execute(
            text("INSERT INTO chairs (table_id, seat) SELECT :id, seat FROM generate_series(1, 3) AS seat"),
            {"id": old_id},
        )

    assert service.view(OPENER, old_id, frozenset()).options == TableOptions(show_running_points=False)


def test_a_table_opened_private_is_listed_to_nobody_and_an_open_one_is_after_a_reload(service):
    listed = service.create(OPENER, CreateTable(command_id="command-1")).id
    service.create(OPENER, CreateTable(command_id="command-2", visibility=Visibility.PRIVATE))

    assert service.open_table_ids() == (TableId(listed),)


def test_a_table_stored_before_visibility_existed_is_open(service, engine):
    old_id = "b" * 32
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES (:id, 1)"), {"id": old_id})
        connection.execute(
            text("INSERT INTO chairs (table_id, seat) SELECT :id, seat FROM generate_series(1, 3) AS seat"),
            {"id": old_id},
        )

    assert service.open_table_ids() == (TableId(old_id),)


def test_an_ended_open_table_is_listed_to_nobody(service):
    table_id = service.create(OPENER, CreateTable(command_id="command-1")).id
    service.close(OPENER, CloseTable("command-close", table_id))

    assert service.open_table_ids() == ()


def test_another_member_reads_the_table_without_a_chair_of_their_own(service):
    created = service.create(OPENER, CreateTable(command_id="command-1"))

    view = service.view(VISITOR, created.id, frozenset())

    assert [chair.is_mine for chair in view.chairs] == [False, False, False]
    assert view.chairs[0].occupant_name == "Anna"


def test_a_retry_with_the_same_command_id_writes_no_second_table(service, engine):
    first = service.create(OPENER, CreateTable(command_id="command-1"))

    assert service.create(OPENER, CreateTable(command_id="command-1")) == first
    assert (count(engine, "tables"), count(engine, "chairs"), count(engine, "receipts")) == (1, 3, 1)


def test_a_command_id_reused_with_another_payload_is_refused_and_writes_nothing(service, engine):
    service.create(OPENER, CreateTable(command_id="command-1"))
    with engine.begin() as connection:
        connection.execute(text("UPDATE receipts SET payload = '{\"seats\": 4}'"))

    command = CreateTable(command_id="command-1")

    with pytest.raises(CommandIdReusedError):
        service.create(OPENER, command)

    assert (count(engine, "tables"), count(engine, "receipts")) == (1, 1)


def test_two_identical_requests_at_once_open_one_table(service, engine):
    answers: list[object] = []
    start = threading.Barrier(2)

    def request():
        start.wait()
        answers.append(service.create(OPENER, CreateTable(command_id="command-1")))

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(answers) == 2
    assert answers[0] == answers[1]
    assert count(engine, "tables") == 1


def test_a_failure_between_the_table_write_and_the_receipt_persists_nothing(engine):
    failing = TableService(
        FaultyTableTransactions(PostgresTableTransactions(engine), receipt_failure=ConnectionError("lost"))
    )

    command = CreateTable(command_id="command-1")

    with pytest.raises(ConnectionError):
        failing.create(OPENER, command)

    assert (count(engine, "tables"), count(engine, "chairs"), count(engine, "receipts")) == (0, 0, 0)


def test_an_identical_request_that_missed_the_committed_receipt_loses_on_the_unique_key_and_replays_the_winner(
    engine,
):
    winner = TableService(PostgresTableTransactions(engine)).create(OPENER, CreateTable(command_id="command-1"))
    blind = TableService(FaultyTableTransactions(PostgresTableTransactions(engine), blind_first_replay=True))

    loser = blind.create(OPENER, CreateTable(command_id="command-1"))

    assert loser == winner
    assert (count(engine, "tables"), count(engine, "chairs"), count(engine, "receipts")) == (1, 3, 1)


def test_table_ids_are_distinct_128_bit_hex_and_not_sequential(service):
    ids = [service.create(OPENER, CreateTable(command_id=f"command-{n}")).id for n in range(5)]

    assert len(set(ids)) == 5
    assert all(len(table_id) == 32 and int(table_id, 16) >= 0 for table_id in ids)
    numbers = [int(table_id, 16) for table_id in ids]
    assert all(abs(later - earlier) > len(ids) for earlier, later in itertools.pairwise(numbers))


CLEO = Actor(account_id="account-cleo", display_name="Cleo")


class TestSeating:
    @pytest.fixture
    def table_id(self, service):
        return service.create(OPENER, CreateTable(command_id="command-open")).id

    def test_a_seat_and_a_stand_read_back_after_a_reload(self, service, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())
        sitting = service.view(OPENER, table_id, frozenset())

        service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())
        standing = service.view(OPENER, table_id, frozenset())

        assert [chair.occupant_name for chair in sitting.chairs] == ["Anna", "Ben", None]
        assert [chair.occupant_name for chair in standing.chairs] == ["Anna", None, None]
        assert (sitting.version, standing.version) == (2, 3)

    def test_a_refusal_and_its_retry_write_no_chair_and_keep_the_first_outcome(self, service, engine, table_id):
        first = service.sit(VISITOR, SitDown("command-sit", table_id, 1), frozenset())
        service.stand(OPENER, StandUp("command-stand", table_id), frozenset())

        again = service.sit(VISITOR, SitDown("command-sit", table_id, 1), frozenset())

        assert (first.refusal, first.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert (again.refusal, again.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert count(engine, "receipts") == 3

    def test_a_command_id_reused_for_another_chair_is_refused(self, service, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())

        reuse = SitDown("command-sit", table_id, 3)

        with pytest.raises(CommandIdReusedError):
            service.sit(VISITOR, reuse, frozenset())

    def test_two_sits_at_once_on_the_last_chair_seat_exactly_one(self, service, engine, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())
        rivals = [Actor("account-cem", "Cem"), Actor("account-dora", "Dora")]
        racing = TableService(BothReadBeforeEitherWrites(PostgresTableTransactions(engine), len(rivals)))
        results = {}

        def sit(rival):
            results[rival.display_name] = racing.sit(rival, SitDown("command-sit", table_id, 3), frozenset())

        threads = [threading.Thread(target=sit, args=(rival,)) for rival in rivals]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        winners = [name for name, result in results.items() if result.refusal is None]
        losers = [result for result in results.values() if result.refusal is not None]
        assert len(winners) == 1
        assert [(loser.refusal, loser.holder) for loser in losers] == [(Refusal.SEAT_TAKEN, winners[0])]
        view = service.view(OPENER, table_id, frozenset())
        assert [chair.occupant_name for chair in view.chairs] == ["Anna", "Ben", winners[0]]
        assert view.version == 3
        assert count(engine, "hand_cards") == len(DECK)

    def test_two_commands_reusing_each_others_command_ids_at_two_tables_are_both_refused(
        self, service, engine, table_id
    ):
        other_id = service.create(OPENER, CreateTable(command_id="command-open-other")).id
        service.sit(VISITOR, SitDown("command-here", table_id, 2), frozenset())
        service.sit(VISITOR, SitDown("command-there", other_id, 2), frozenset())
        racing = TableService(BothReadBeforeEitherWrites(PostgresTableTransactions(engine), 2, rivals_must_meet=True))
        outcomes = []

        def reuse(command_id, at_table):
            try:
                racing.sit(VISITOR, SitDown(command_id, at_table, 3), frozenset())
            except Exception as error:
                outcomes.append(type(error))

        threads = [
            threading.Thread(target=reuse, args=("command-there", table_id)),
            threading.Thread(target=reuse, args=("command-here", other_id)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert outcomes == [CommandIdReusedError, CommandIdReusedError]

    def test_a_failure_after_the_chair_write_persists_nothing(self, engine, table_id):
        failing = TableService(
            FaultyTableTransactions(PostgresTableTransactions(engine), receipt_failure=ConnectionError("lost"))
        )

        sitting = SitDown("command-sit", table_id, 2)

        with pytest.raises(ConnectionError):
            failing.sit(VISITOR, sitting, frozenset())

        view = TableService(PostgresTableTransactions(engine)).view(OPENER, table_id, frozenset())
        assert ([chair.occupant_name for chair in view.chairs], view.version) == (["Anna", None, None], 1)
        assert count(engine, "receipts") == 1

    def test_a_command_id_reused_on_another_table_that_missed_the_receipt_is_refused_on_the_unique_key(
        self, service, engine, table_id
    ):
        other_id = service.create(OPENER, CreateTable(command_id="command-other")).id
        service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())
        blind = TableService(FaultyTableTransactions(PostgresTableTransactions(engine), blind_first_replay=True))
        receipts_before = count(engine, "receipts")

        reuse = SitDown("command-sit", other_id, 2)

        with pytest.raises(CommandIdReusedError):
            blind.sit(VISITOR, reuse, frozenset())

        view = service.view(OPENER, other_id, frozenset())
        assert ([chair.occupant_name for chair in view.chairs], view.version) == (["Anna", None, None], 1)
        assert count(engine, "receipts") == receipts_before


class TestHand:
    @pytest.fixture
    def dealing(self, engine):
        return TableService(
            PostgresTableTransactions(engine),
            random_source=random.Random(8),  # noqa: S311 - a seeded source makes the deal reproducible
        )

    def seat_three(self, service):
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        service.sit(VISITOR, SitDown("command-ben", table_id, 2), frozenset())
        result = service.sit(CLEO, SitDown("command-cleo", table_id, 3), frozenset())
        return table_id, result

    def stored(self, engine, table_id):
        with PostgresTableTransactions(engine).begin() as transaction:
            return transaction.table(TableId(table_id))

    def cards_by_holder(self, record):
        held = {position: set(cards) for position, cards in record.hand.hands.items()}
        return held, set(record.hand.skat)

    def test_the_third_sit_stores_the_dealer_and_all_thirty_two_cards_once(self, dealing, engine):
        table_id, result = self.seat_three(dealing)

        record = self.stored(engine, table_id)
        held, skat = self.cards_by_holder(record)
        assert result.refusal is None
        assert record.dealer in SEATS
        assert [len(cards) for cards in held.values()] == [10, 10, 10]
        assert len(skat) == 2
        assert set().union(skat, *held.values()) == set(DECK)
        assert (record.version, count(engine, "hand_cards"), count(engine, "receipts")) == (3, 32, 3)

    def test_a_hand_saved_after_a_dealer_without_a_hand_reads_back(self, dealing, engine):
        dealt_id, _ = self.seat_three(dealing)
        dealt = self.stored(engine, dealt_id)
        other_id = dealing.create(OPENER, CreateTable(command_id="command-other")).id
        other = self.stored(engine, other_id)
        with PostgresTableTransactions(engine).begin() as transaction:
            transaction.save_table(replace(other, dealer=dealt.dealer), played_at=datetime(2026, 11, 1, 12, tzinfo=UTC))
        with PostgresTableTransactions(engine).begin() as transaction:
            transaction.save_table(replace(other, dealer=dealt.dealer, hand=dealt.hand), played_at=None)

        record = self.stored(engine, other_id)
        assert (record.dealer, record.hand) == (dealt.dealer, dealt.hand)

    def test_a_fresh_store_reads_the_identical_hand_and_dealer(self, dealing, engine, database_url):
        table_id, _ = self.seat_three(dealing)
        before = self.stored(engine, table_id)

        restarted = create_store_engine(database_url)
        try:
            after = self.stored(restarted, table_id)
        finally:
            restarted.dispose()

        assert after.dealer == before.dealer
        assert self.cards_by_holder(after) == self.cards_by_holder(before)

    def test_a_hand_reads_each_holders_cards_in_deck_order(self, dealing, engine):
        table_id, _ = self.seat_three(dealing)

        record = self.stored(engine, table_id)

        for cards in (*record.hand.hands.values(), record.hand.skat):
            assert list(cards) == sorted(cards, key=DECK.index)
        assert set(record.hand.hands) == set(Position)

    def test_a_table_before_its_third_sit_has_no_dealer_and_no_hand(self, dealing, engine):
        table_id = dealing.create(OPENER, CreateTable(command_id="command-open")).id
        dealing.sit(VISITOR, SitDown("command-ben", table_id, 2), frozenset())

        record = self.stored(engine, table_id)

        assert (record.dealer, record.hand, count(engine, "hand_cards")) == (None, None, 0)

    def test_a_retry_of_the_third_sit_and_a_fourth_sit_write_no_second_hand(self, dealing, engine):
        table_id, first = self.seat_three(dealing)
        dealt = self.stored(engine, table_id)

        again = dealing.sit(CLEO, SitDown("command-cleo", table_id, 3), frozenset())
        late = dealing.sit(Actor("account-dora", "Dora"), SitDown("command-dora", table_id, 2), frozenset())

        assert again == first
        assert late.refusal is Refusal.SEAT_TAKEN
        assert self.stored(engine, table_id) == dealt
        assert count(engine, "hand_cards") == 32

    def test_standing_up_while_a_hand_runs_stores_the_open_chair_beside_the_hand_a_restart_reads_back(
        self, dealing, engine
    ):
        table_id, _ = self.seat_three(dealing)
        dealt = self.stored(engine, table_id)

        result = dealing.stand(VISITOR, StandUp("command-stand", table_id), frozenset())

        stored = self.stored(engine, table_id)
        assert result.refusal is None
        assert (stored.hand, stored.progress.auction, stored.version) == (
            dealt.hand,
            dealt.progress.auction,
            dealt.version + 1,
        )
        assert [chair.occupant is None for chair in stored.chairs] == [False, True, False]
        assert stored.progress.seats_held == {SeatHeld(VISITOR.account_id, 2)}

    def test_a_failure_during_the_third_sit_stores_no_chair_no_hand_no_dealer_and_no_receipt(self, engine, dealing):
        table_id = dealing.create(OPENER, CreateTable(command_id="command-open")).id
        dealing.sit(VISITOR, SitDown("command-ben", table_id, 2), frozenset())
        failing = TableService(
            FaultyTableTransactions(PostgresTableTransactions(engine), receipt_failure=ConnectionError("lost")),
            random_source=random.Random(8),  # noqa: S311 - a seeded source makes the deal reproducible
        )

        sitting = SitDown("command-cleo", table_id, 3)

        with pytest.raises(ConnectionError):
            failing.sit(CLEO, sitting, frozenset())

        record = self.stored(engine, table_id)
        assert [chair.occupant is None for chair in record.chairs] == [False, False, True]
        assert (record.dealer, record.hand, record.version) == (None, None, 2)
        assert (count(engine, "hand_cards"), count(engine, "receipts")) == (0, 2)


class TestOccupiedChairs:
    def test_reads_every_occupied_chair_and_no_free_one(self, service, engine):
        first = service.create(OPENER, CreateTable(command_id="command-first")).id
        service.sit(VISITOR, SitDown("command-ben", first, 3), frozenset())
        second = service.create(VISITOR, CreateTable(command_id="command-second")).id
        service.stand(VISITOR, StandUp("command-stand", second), frozenset())

        assert {(chair.table_id.value, chair.account_id) for chair in service.occupied_chairs()} == {
            (first, OPENER.account_id),
            (first, VISITOR.account_id),
        }

    def test_frees_a_chair_in_the_store_and_keeps_the_receipts(self, service, engine):
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        service.sit(VISITOR, SitDown("command-ben", table_id, 3), frozenset())
        receipts_before = count(engine, "receipts")

        freed = service.free_chair(TableId(table_id), VISITOR.account_id, nullcontext(enter_result=True))

        view = service.view(OPENER, table_id, frozenset())
        assert (freed, [chair.occupant_name for chair in view.chairs], view.version) == (True, ["Anna", None, None], 3)
        assert count(engine, "receipts") == receipts_before

    def test_the_caller_stays_in_charge_until_the_freeing_is_committed(self, service):
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        service.sit(VISITOR, SitDown("command-ben", table_id, 3), frozenset())
        occupants_when_released = []

        @contextmanager
        def due_until_released():
            yield True
            view = service.view(OPENER, table_id, frozenset())
            occupants_when_released.append([chair.occupant_name for chair in view.chairs])

        service.free_chair(TableId(table_id), VISITOR.account_id, due_until_released())

        assert occupants_when_released == [["Anna", None, None]]


class TestDealtHandStays:
    @pytest.fixture
    def dealt(self, service, engine):
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        service.sit(VISITOR, SitDown("command-visitor", table_id, 2), frozenset())
        service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())
        transactions = PostgresTableTransactions(engine)
        with transactions.begin() as transaction:
            return transactions, transaction.table(TableId(table_id))

    def other_hand(self, record):
        hand = record.hand
        return replace(
            hand,
            forehand=(hand.middlehand[0], *hand.forehand[1:]),
            middlehand=(hand.forehand[0], *hand.middlehand[1:]),
        )

    @pytest.fixture(params=[False, True], ids=["another hand", "no hand"])
    def differing_hand(self, request, dealt):
        _, record = dealt
        return None if request.param else self.other_hand(record)

    def read(self, transactions, record):
        with transactions.begin() as transaction:
            return transaction.table(record.id)

    def test_a_differing_hand_raises_while_the_hand_has_progress(self, dealt, differing_hand):
        transactions, record = dealt
        changed = replace(
            record,
            hand=differing_hand,
            version=record.version + 1,
            progress=HandProgress(auction=(Bid(Position.MIDDLEHAND, 18),)),
        )

        def save():
            with transactions.begin() as transaction:
                transaction.save_table(changed, played_at=None)

        with pytest.raises(DealtHandRewrittenError):
            save()

        assert self.read(transactions, record) == record

    def test_a_differing_hand_without_progress_leaves_the_stored_hand_alone(self, dealt, differing_hand):
        transactions, record = dealt
        changed = replace(record, hand=differing_hand, version=record.version + 1)

        with transactions.begin() as transaction:
            transaction.save_table(changed, played_at=None)

        assert self.read(transactions, record).hand == record.hand


ALL_THREE = frozenset({OPENER.account_id, VISITOR.account_id, THIRD_PLAYER.account_id})


class TestDealNext:
    @pytest.fixture
    def transactions(self, engine):
        return PostgresTableTransactions(engine)

    @staticmethod
    def seated(service):
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        service.sit(VISITOR, SitDown("command-visitor", table_id, 2), frozenset())
        service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())
        return table_id

    @pytest.fixture
    def table_id(self, service, transactions):
        table_id = self.seated(service)
        record = self.read(transactions, table_id)
        by_position = {
            position: {1: OPENER, 2: VISITOR, 3: THIRD_PLAYER}[seat]
            for seat, position in positions_from(record.dealer).items()
        }
        for step, position in enumerate((Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND)):
            command = AuctionCommand(f"command-pass-{step}", table_id, record.version + step, AuctionAction.PASS, None)
            service.take_auction_step(by_position[position], command, frozenset())
        return table_id

    def read(self, transactions, table_id):
        with transactions.begin() as transaction:
            return transaction.table(TableId(table_id))

    def test_the_deal_stores_the_next_dealers_hand_clears_the_steps_and_writes_no_receipt_in_one_bump(
        self, service, transactions, engine, table_id
    ):
        before = self.read(transactions, table_id)
        receipts_before = count(engine, "receipts")

        assert service.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is True

        after = self.read(transactions, table_id)
        assert (after.version, after.dealer) == (before.version + 1, next_dealer(before.dealer))
        assert after.progress == HandProgress()
        assert count(engine, "hand_cards") == len(DECK)
        assert count(engine, "auction_actions") == 0
        assert count(engine, "receipts") == receipts_before

    def test_the_caller_stays_in_charge_until_the_deal_is_committed(self, service, transactions, table_id):
        before = self.read(transactions, table_id)
        versions_when_released = []

        @contextmanager
        def connected_until_released():
            yield ALL_THREE
            versions_when_released.append(self.read(transactions, table_id).version)

        service.deal_next(TableId(table_id), connected_until_released())

        assert versions_when_released == [before.version + 1]

    def test_a_stand_and_a_new_sit_during_the_pause_deal_and_the_ending_pause_then_changes_nothing(
        self, service, transactions, engine, table_id
    ):
        before = self.read(transactions, table_id)
        newcomer = Actor("account-new", "Nora")
        service.stand(THIRD_PLAYER, StandUp("command-stand", table_id), frozenset())
        service.sit(newcomer, SitDown("command-new", table_id, 3), frozenset())
        dealt = self.read(transactions, table_id)

        dealt_again = service.deal_next(TableId(table_id), nullcontext(ALL_THREE | {newcomer.account_id}))

        assert dealt.dealer == next_dealer(before.dealer)
        assert dealt_again is False
        assert self.read(transactions, table_id) == dealt
        assert count(engine, "hand_cards") == len(DECK)

    def test_two_checks_at_once_deal_once_and_bump_the_version_once(self, transactions, engine, table_id):
        before = self.read(transactions, table_id)
        racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
        answers = []

        def check():
            answers.append(racing.deal_next(TableId(table_id), nullcontext(ALL_THREE)))

        threads = [threading.Thread(target=check), threading.Thread(target=check)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(answers) == [False, True]
        assert self.read(transactions, table_id).version == before.version + 1
        assert count(engine, "hand_cards") == len(DECK)

    def test_a_failure_in_the_deal_persists_nothing(self, transactions, engine, table_id):
        before = self.read(transactions, table_id)
        failing = TableService(FaultyTableTransactions(transactions, save_failure=ConnectionError("lost")))
        identifier = TableId(table_id)
        everyone = nullcontext(ALL_THREE)

        with pytest.raises(ConnectionError):
            failing.deal_next(identifier, everyone)

        assert self.read(transactions, table_id) == before
        assert count(engine, "hand_cards") == 0


class TestReadyMarks:
    @pytest.fixture
    def table_id(self, service, transactions, stored):
        """Three seated after their first game, its result pending."""
        table_id = TestDealNext.seated(service)
        with transactions.begin() as transaction:
            transaction.save_table(after_the_first_game(stored(transactions, table_id)), played_at=None)
        return table_id

    def tap(self, service, actor, table_id, command_id):
        return service.mark_ready(actor, ReadyCommand(command_id, table_id, 1, 1), frozenset())

    def test_the_marks_read_back_and_standing_up_clears_only_the_own(self, service, transactions, stored, table_id):
        self.tap(service, OPENER, table_id, "weiter-anna")
        self.tap(service, VISITOR, table_id, "weiter-ben")
        marked = [chair.ready for chair in stored(transactions, table_id).chairs]
        service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())

        after = stored(transactions, table_id).chairs
        assert (marked, [chair.ready for chair in after]) == ([True, True, False], [True, False, False])

    def test_the_last_tap_and_a_repeated_one_at_once_deal_once(self, service, transactions, engine, stored, table_id):
        self.tap(service, OPENER, table_id, "weiter-anna")
        self.tap(service, VISITOR, table_id, "weiter-ben")
        before = stored(transactions, table_id)
        racing = TableService(BothReadBeforeEitherWrites(transactions, 2))

        def tap_and_deal(actor):
            self.tap(racing, actor, table_id, "weiter-again")
            racing.deal_next(TableId(table_id), nullcontext(ALL_THREE))

        threads = [threading.Thread(target=tap_and_deal, args=(actor,)) for actor in (THIRD_PLAYER, VISITOR)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        after = stored(transactions, table_id)
        assert after.version == before.version + 2
        assert [chair.ready for chair in after.chairs] == [False, False, False]
        assert count(engine, "hand_cards") == len(DECK)


def pass_in_by_turn(server, table_id, people):
    """Each seated member passes when the view names their turn."""
    url = f"{TABLES_PATH}/{table_id}"
    for step in range(3):
        view = server.client.get(url, headers=people[0][0]).json()
        server.client.cookies.clear()
        headers = people[view["hand"]["auction"]["turn_seat"] - 1][0]
        answer = server.client.post(
            url + TABLE_AUCTION_PASS_SUFFIX,
            json={"command_id": f"pass-{step:04d}", "version": view["version"]},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )
        server.client.cookies.clear()
        assert answer.status_code == 200, answer.text


def test_a_restart_during_the_pause_deals_once_when_all_three_streams_reopen_with_no_sweep(sign_in_settings, engine):
    settings = sign_in_settings()
    time = FakeTime()
    transactions = PostgresTableTransactions(engine)

    def server_on(stores):
        return Skat(lambda: settings, store=transactions, stores=stores, chair_clock=time.clock, chair_scheduler=time)

    before_restart = server_on(None)
    with before_restart.client:
        people = [before_restart.member() for _ in range(3)]
        table_id = before_restart.create(people[0][0]).json()["id"]
        for seat, (headers, _) in enumerate(people[1:], start=2):
            before_restart.sit(headers, table_id, seat, command_id=f"command-sit-{seat}")
        before_restart.client.cookies.clear()
        pass_in_by_turn(before_restart, table_id, people)

    def table(server):
        return server.client.get(f"{TABLES_PATH}/{table_id}", headers=people[0][0]).json()

    after_restart = server_on(before_restart.stores)
    with after_restart.client:
        after_restart.client.portal.call(time.advance, NEXT_DEAL_PAUSE_SECONDS * 2)
        waiting = table(after_restart)
        assert waiting["hand"] is None
        after_restart.client.cookies.clear()

        with streams_of(after_restart, table_id, people):
            after_restart.client.portal.call(time.advance, NEXT_DEAL_PAUSE_SECONDS)

        dealt = table(after_restart)
        assert (dealt["version"], dealt["passed_in"]) == (waiting["version"] + 1, None)
        assert dealt["hand"] is not None
        after_restart.client.portal.call(time.advance, NEXT_DEAL_PAUSE_SECONDS * 2)
        assert table(after_restart)["version"] == dealt["version"]
