"""A member's turn statement is stored on its chair under the table's row lock: it survives a restart, leaves the
version alone, outlives a move saved beside it, goes with the seat and is read only while its account sits there.
"""

import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from skat.store.schema import chairs
from skat.store.tables import PostgresTableTransactions
from skat.table.records import StandUp, TurnStatement
from skat.table.rules import with_occupant
from skat.table.service import TableService
from tests.support.seated_tables import NOBODY_CONNECTED, OPENER, SEATED, seated_table
from tests.support.table_rows import WorkInAThread, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

MEMBER = SEATED[1]
MEMBERS_SEAT = 2
OPENERS_SEAT = 1
STEP_SECONDS = 5
STATED_AT = datetime(2026, 11, 19, 12, tzinfo=UTC)


@pytest.fixture
def clock():
    """The times the service stamps, newest last; a test appends the next time it wants stamped."""
    return [STATED_AT]


@pytest.fixture
def timed_service(transactions, clock):
    return TableService(transactions, random_source=random.Random(8), now=lambda: clock[-1])  # noqa: S311 - a seeded source makes the deal reproducible


@pytest.fixture
def table_id(service):
    return seated_table(service, "turn-state")


def statement_of(stored, transactions, table_id, seat=MEMBERS_SEAT):
    return stored(transactions, table_id.value).chairs[seat - 1].turn_state


def statement_columns(engine, table_id):
    with engine.connect() as connection:
        return {
            row.seat: (row.turn_state_account, row.turn_state_stopped, row.turn_state_thinking, row.turn_state_at)
            for row in connection.execute(select(chairs).where(chairs.c.table_id == table_id.value))
        }


def test_a_statement_is_stored_for_its_seat_and_survives_a_restart(service, engine, stored, table_id):
    service.set_turn_state(MEMBER.account_id, table_id.value, "budget_spent", False)

    restarted = PostgresTableTransactions(engine)

    statement = statement_of(stored, restarted, table_id)
    assert (statement.stopped, statement.thinking) == ("budget_spent", False)
    assert statement_of(stored, restarted, table_id, OPENERS_SEAT) is None


def test_stating_leaves_the_stored_version_alone(service, transactions, stored, table_id):
    version = stored(transactions, table_id.value).version

    service.set_turn_state(MEMBER.account_id, table_id.value, None, True)

    assert stored(transactions, table_id.value).version == version


def test_a_move_saved_after_a_statement_keeps_it(service, transactions, stored, table_id):
    service.set_turn_state(MEMBER.account_id, table_id.value, "busy", False)

    service.stand(OPENER, StandUp("stand-opener", table_id.value), NOBODY_CONNECTED)

    assert statement_of(stored, transactions, table_id).stopped == "busy"
    assert stored(transactions, table_id.value).chairs[OPENERS_SEAT - 1].occupant is None


def test_a_statement_made_while_a_move_holds_the_table_waits_for_it_and_both_are_kept(
    service, engine, transactions, stored, table_id
):
    statement = WorkInAThread(lambda: service.set_turn_state(MEMBER.account_id, table_id.value, "busy", False))
    with transactions.begin() as moving:
        table = moving.locked_table(table_id)
        statement.start()
        wait_until_a_session_waits_for_a_lock(engine, statement)
        moving.save_table(with_occupant(table, OPENERS_SEAT, None), played_at=None)
    statement.join(STEP_SECONDS)

    record = stored(transactions, table_id.value)
    assert statement.outcome == [True]
    assert record.chairs[OPENERS_SEAT - 1].occupant is None
    assert record.chairs[MEMBERS_SEAT - 1].turn_state.stopped == "busy"
    assert record.version == table.version + 1


def test_the_columns_are_cleared_when_the_seat_ends(service, engine, table_id):
    service.set_turn_state(MEMBER.account_id, table_id.value, "busy", False)
    assert statement_columns(engine, table_id)[MEMBERS_SEAT][0] == MEMBER.account_id

    service.stand(MEMBER, StandUp("stand-member", table_id.value), NOBODY_CONNECTED)

    assert statement_columns(engine, table_id)[MEMBERS_SEAT] == (None, None, None, None)


def test_a_statement_of_an_account_that_no_longer_sits_there_is_not_read_and_the_next_save_clears_it(
    service, engine, transactions, stored, table_id
):
    service.set_turn_state(MEMBER.account_id, table_id.value, "busy", False)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE chairs SET account_id = 'account-dora', display_name = 'Dora' WHERE seat = :seat"),
            {"seat": MEMBERS_SEAT},
        )

    assert statement_of(stored, transactions, table_id) is None

    service.stand(OPENER, StandUp("stand-opener", table_id.value), NOBODY_CONNECTED)

    assert statement_columns(engine, table_id)[MEMBERS_SEAT] == (None, None, None, None)


def times_of(transactions, read):
    with transactions.begin() as transaction:
        return read(transaction)[0].turn_statement_times


def test_the_index_reads_tell_the_statement_times_of_a_table_while_their_accounts_sit_there(
    timed_service, engine, transactions, stored, table_id
):
    def of_the_table(transaction):
        return transaction.versions_of([table_id])

    def of_the_members_tables(transaction):
        return transaction.tables_of(MEMBER.account_id)

    assert times_of(transactions, of_the_table) == ()
    timed_service.set_turn_state(MEMBER.account_id, table_id.value, "busy", False)

    assert times_of(transactions, of_the_table) == (STATED_AT,)
    assert times_of(transactions, of_the_members_tables) == (STATED_AT,)

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE chairs SET account_id = 'account-dora', display_name = 'Dora' WHERE seat = :seat"),
            {"seat": MEMBERS_SEAT},
        )

    assert times_of(transactions, of_the_table) == ()


def test_a_statement_stamped_earlier_than_another_chairs_still_changes_the_statement_times(
    clock, timed_service, transactions, table_id
):
    def of_the_table(transaction):
        return transaction.versions_of([table_id])

    clock.append(STATED_AT + timedelta(seconds=10))
    timed_service.set_turn_state(OPENER.account_id, table_id.value, "busy", False)
    after_the_opener = times_of(transactions, of_the_table)

    clock.append(STATED_AT)
    timed_service.set_turn_state(MEMBER.account_id, table_id.value, "busy", False)

    assert times_of(transactions, of_the_table) != after_the_opener


def test_the_statement_time_is_stored_as_given(service, engine, transactions, stored, table_id):
    service.set_turn_state(MEMBER.account_id, table_id.value, None, True)

    statement = statement_of(stored, transactions, table_id)

    assert isinstance(statement, TurnStatement)
    assert statement.stated_at.tzinfo is not None
