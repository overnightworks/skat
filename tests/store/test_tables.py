import itertools
import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CreateTable
from skat.table.service import CommandIdReusedError, TableService

pytestmark = pytest.mark.postgres

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


def count(engine, table):
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_a_created_table_reads_back_the_same_after_a_reload(service):
    created = service.create(OPENER, CreateTable(command_id="command-1"))

    assert service.view(OPENER, created.id) == created
    assert [(chair.seat, chair.occupant_name) for chair in created.chairs] == [(1, "Anna"), (2, None), (3, None)]


def test_another_member_reads_the_table_without_a_chair_of_their_own(service):
    created = service.create(OPENER, CreateTable(command_id="command-1"))

    view = service.view(VISITOR, created.id)

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

    with pytest.raises(CommandIdReusedError):
        service.create(OPENER, CreateTable(command_id="command-1"))

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
    class FailingReceipts(PostgresTableTransactions):
        @contextmanager
        def begin(self):
            with super().begin() as transaction:
                transaction.add_receipt = self._fail
                yield transaction

        @staticmethod
        def _fail(receipt):
            raise ConnectionError("lost")

    failing = TableService(FailingReceipts(engine))

    with pytest.raises(ConnectionError):
        failing.create(OPENER, CreateTable(command_id="command-1"))

    assert (count(engine, "tables"), count(engine, "chairs"), count(engine, "receipts")) == (0, 0, 0)


def test_table_ids_are_distinct_128_bit_hex_and_not_sequential(service):
    ids = [service.create(OPENER, CreateTable(command_id=f"command-{n}")).id for n in range(5)]

    assert len(set(ids)) == 5
    assert all(len(table_id) == 32 and int(table_id, 16) >= 0 for table_id in ids)
    numbers = [int(table_id, 16) for table_id in ids]
    assert all(abs(later - earlier) > len(ids) for earlier, later in itertools.pairwise(numbers))
