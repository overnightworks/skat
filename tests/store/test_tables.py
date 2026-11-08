import itertools
import threading
from contextlib import contextmanager, suppress

import pytest
from sqlalchemy import func, select, table, text

from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CreateTable, Refusal, SitDown, StandUp
from skat.table.service import CommandIdReusedError, TableService
from tests.support.faulty_tables import FaultyTableTransactions

pytestmark = pytest.mark.postgres

BARRIER_TIMEOUT_SECONDS = 0.5

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")


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


class ReceiptsThatFail:
    """The real transactions, except that storing a receipt raises: the chair is written by then."""

    def __init__(self, inner):
        self._inner = inner

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            transaction.add_receipt = _lose_connection
            yield transaction


def _lose_connection(_receipt):
    raise ConnectionError("lost")


class BothReadBeforeEitherWrites:
    """Holds each command after its locking read until its rival has read too, if the rival can.

    Without a row lock both rivals read the free chair and both would write; with it the second waits
    outside, the barrier breaks after its timeout and the first goes on alone.
    """

    def __init__(self, inner, rivals):
        self._inner = inner
        self._barrier = threading.Barrier(rivals, timeout=BARRIER_TIMEOUT_SECONDS)

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            locked_table = transaction.locked_table

            def read_then_wait(table_id):
                table = locked_table(table_id)
                with suppress(threading.BrokenBarrierError):
                    self._barrier.wait()
                return table

            transaction.locked_table = read_then_wait
            yield transaction


class TestSeating:
    @pytest.fixture
    def table_id(self, service):
        return service.create(OPENER, CreateTable(command_id="command-open")).id

    def test_a_seat_and_a_stand_read_back_after_a_reload(self, service, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id, 2))
        sitting = service.view(OPENER, table_id, frozenset())

        service.stand(VISITOR, StandUp("command-stand", table_id))
        standing = service.view(OPENER, table_id, frozenset())

        assert [chair.occupant_name for chair in sitting.chairs] == ["Anna", "Ben", None]
        assert [chair.occupant_name for chair in standing.chairs] == ["Anna", None, None]
        assert (sitting.version, standing.version) == (2, 3)

    def test_a_refusal_and_its_retry_write_no_chair_and_keep_the_first_outcome(self, service, engine, table_id):
        first = service.sit(VISITOR, SitDown("command-sit", table_id, 1))
        service.stand(OPENER, StandUp("command-stand", table_id))

        again = service.sit(VISITOR, SitDown("command-sit", table_id, 1))

        assert (first.refusal, first.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert (again.refusal, again.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert count(engine, "receipts") == 3

    def test_a_command_id_reused_for_another_chair_is_refused(self, service, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id, 2))

        with pytest.raises(CommandIdReusedError):
            service.sit(VISITOR, SitDown("command-sit", table_id, 3))

    def test_two_sits_at_once_on_the_last_chair_seat_exactly_one(self, service, engine, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id, 2))
        rivals = [Actor("account-cem", "Cem"), Actor("account-dora", "Dora")]
        racing = TableService(BothReadBeforeEitherWrites(PostgresTableTransactions(engine), len(rivals)))
        results = {}

        def sit(rival):
            results[rival.display_name] = racing.sit(rival, SitDown("command-sit", table_id, 3))

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

    def test_a_failure_after_the_chair_write_persists_nothing(self, engine, table_id):
        failing = TableService(ReceiptsThatFail(PostgresTableTransactions(engine)))

        with pytest.raises(ConnectionError):
            failing.sit(VISITOR, SitDown("command-sit", table_id, 2))

        view = TableService(PostgresTableTransactions(engine)).view(OPENER, table_id, frozenset())
        assert ([chair.occupant_name for chair in view.chairs], view.version) == (["Anna", None, None], 1)
        assert count(engine, "receipts") == 1

    def test_a_view_does_not_wait_for_a_command_holding_the_table_row(self, service, engine, table_id):
        with engine.begin() as holder:
            holder.execute(text("SELECT id FROM tables WHERE id = :id FOR UPDATE"), {"id": table_id})

            assert service.view(OPENER, table_id, frozenset()) is not None
