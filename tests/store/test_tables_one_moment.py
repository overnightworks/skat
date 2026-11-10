import random
import threading
from contextlib import suppress
from dataclasses import replace

import pytest
from sqlalchemy import event, text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CreateTable, SitDown, TableId
from skat.table.service import TableService
from tests.support.faulty_tables import WAIT_DEADLINE_SECONDS
from tests.support.table_rows import WorkInAThread, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")


def run_in_thread(work):
    thread = WorkInAThread(work)
    thread.start()
    return thread, thread.outcome


class TestOneMomentRead:
    @pytest.fixture
    def dealt(self, engine):
        dealing = TableService(PostgresTableTransactions(engine), random_source=random.Random(8))  # noqa: S311 - seeded
        table_id = dealing.create(OPENER, CreateTable(command_id="command-dealt")).id
        dealing.sit(VISITOR, SitDown("command-ben", table_id, 2), frozenset())
        dealing.sit(CLEO, SitDown("command-cleo", table_id, 3), frozenset())
        return self.read(engine, table_id)

    @pytest.fixture
    def table_id(self, service):
        return service.create(OPENER, CreateTable(command_id="command-open")).id

    def read(self, engine, table_id):
        with PostgresTableTransactions(engine).begin() as transaction:
            return transaction.table(TableId(table_id))

    def test_a_read_during_the_deal_waits_and_returns_the_dealer_and_every_card_together(self, engine, table_id, dealt):
        with PostgresTableTransactions(engine).begin() as writer:
            empty = writer.locked_table(TableId(table_id))
            writer.save_table(replace(empty, version=2, dealer=dealt.dealer, hand=dealt.hand))
            reader, outcome = run_in_thread(lambda: self.read(engine, table_id))

            wait_until_a_session_waits_for_a_lock(engine, reader)

        reader.join()
        assert (outcome[0].dealer, outcome[0].hand, outcome[0].version) == (dealt.dealer, dealt.hand, 2)

    def test_a_read_that_waited_for_a_rolled_back_deal_returns_the_table_as_it_was(self, engine, table_id, dealt):
        with suppress(RuntimeError), PostgresTableTransactions(engine).begin() as writer:
            empty = writer.locked_table(TableId(table_id))
            writer.save_table(replace(empty, version=2, dealer=dealt.dealer, hand=dealt.hand))
            reader, outcome = run_in_thread(lambda: self.read(engine, table_id))
            wait_until_a_session_waits_for_a_lock(engine, reader)
            raise RuntimeError("rolled back")

        reader.join()
        assert (outcome[0].dealer, outcome[0].hand, outcome[0].version) == (None, None, 1)

    def test_a_replayed_create_during_the_deal_waits_and_returns_the_dealer_and_hand_together(
        self, engine, table_id, dealt
    ):
        def replay_create():
            with PostgresTableTransactions(engine).begin() as transaction:
                return transaction.replay(OPENER.account_id, "command-open").table

        with PostgresTableTransactions(engine).begin() as writer:
            empty = writer.locked_table(TableId(table_id))
            writer.save_table(replace(empty, version=2, dealer=dealt.dealer, hand=dealt.hand))
            reader, outcome = run_in_thread(replay_create)

            wait_until_a_session_waits_for_a_lock(engine, reader)

        reader.join()
        assert (outcome[0].dealer, outcome[0].hand, outcome[0].version) == (dealt.dealer, dealt.hand, 2)

    def test_a_writer_waits_for_a_read_to_finish(self, engine, table_id):
        def write():
            with PostgresTableTransactions(engine).begin() as writer:
                record = writer.locked_table(TableId(table_id))
                writer.save_table(replace(record, version=2))

        with PostgresTableTransactions(engine).begin() as reading:
            reading.table(TableId(table_id))
            writer, _ = run_in_thread(write)

            wait_until_a_session_waits_for_a_lock(engine, writer)

        writer.join()
        assert self.read(engine, table_id).version == 2

    def test_the_wait_for_a_lock_raises_the_failure_of_a_reader_that_stopped_before_waiting(self, engine):
        def fail():
            raise ConnectionError("lost")

        reader, _ = run_in_thread(fail)

        with pytest.raises(ConnectionError):
            wait_until_a_session_waits_for_a_lock(engine, reader)

    def test_the_wait_for_a_lock_fails_when_the_reader_ends_without_waiting(self, engine):
        reader, _ = run_in_thread(lambda: None)

        with pytest.raises(pytest.fail.Exception, match="without a session waiting"):
            wait_until_a_session_waits_for_a_lock(engine, reader)

    def test_the_wait_for_a_lock_sees_a_session_that_starts_waiting_after_its_first_poll(self, engine):
        first_poll_done = threading.Event()

        @event.listens_for(engine, "after_cursor_execute")
        def release_the_reader_after_the_first_poll(*arguments):
            if "pg_stat_activity" in arguments[2]:
                first_poll_done.set()

        def wait_for_the_advisory_lock():
            first_poll_done.wait()
            with engine.begin() as connection:
                connection.execute(text("SELECT pg_advisory_xact_lock(246)"))

        with engine.begin() as holder:
            holder.execute(text("SELECT pg_advisory_xact_lock(246)"))
            reader, _ = run_in_thread(wait_for_the_advisory_lock)

            wait_until_a_session_waits_for_a_lock(engine, reader, deadline_seconds=5)

        reader.join()

    def test_two_reads_at_once_do_not_wait_for_each_other(self, engine, table_id):
        with PostgresTableTransactions(engine).begin() as first:
            first.table(TableId(table_id))
            second, outcome = run_in_thread(lambda: self.read(engine, table_id))

            second.join(timeout=WAIT_DEADLINE_SECONDS)

            assert not second.is_alive()
        assert outcome[0].version == 1

    def test_a_read_of_a_table_that_does_not_exist_returns_nothing(self, engine):
        assert self.read(engine, "0" * 32) is None
