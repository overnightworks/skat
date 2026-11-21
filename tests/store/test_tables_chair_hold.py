"""A chair hold is a deadline stored beside the table, on the database's clock: a leave writes it, an arrival clears
it, and the freeing, under the table's row lock, frees the chair once and drops it.
"""

import threading
from contextlib import contextmanager, nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, insert, select

from skat.store.schema import chair_holds
from skat.table.records import TableId
from skat.web.presence_roster import PresenceUnknownError
from tests.support.seated_tables import (
    ENDED_AT,
    NOBODY_CONNECTED,
    OPENER,
    SEATED,
    ended_at,
    seated_table,
    undealt_table,
)
from tests.support.table_rows import WorkInAThread, rows_of, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

HOLD_SECONDS = 300
LEAVER = SEATED[1]
# The longest a step of the test may take between the store's clock and the assertion.
STEP_SECONDS = 5
ABSENT = True
PRESENT = False
STOPPED = None


def hold_due_in(engine, table_id, account_id, seconds):
    """A hold of the account's chair that the store finds due `seconds` from now; a negative count is overdue."""
    with engine.begin() as connection:
        connection.execute(delete(chair_holds).where(chair_holds.c.account_id == account_id))
        connection.execute(
            insert(chair_holds).values(
                table_id=table_id.value,
                account_id=account_id,
                due_at=func.now() + timedelta(seconds=seconds),
            )
        )


def seconds_left(engine, table_id, account_id):
    """The seconds until the stored hold is due, on the store's clock, or None without a hold."""
    with engine.connect() as connection:
        return connection.execute(
            select(func.extract("epoch", chair_holds.c.due_at - func.now())).where(
                chair_holds.c.table_id == table_id.value, chair_holds.c.account_id == account_id
            )
        ).scalar_one_or_none()


def holds(engine):
    with engine.connect() as connection:
        return {tuple(row) for row in connection.execute(select(chair_holds.c.table_id, chair_holds.c.account_id))}


def occupants(service, table_id):
    view = service.view(OPENER, table_id.value, NOBODY_CONNECTED)
    return [chair.occupant_name for chair in view.chairs]


def version_of(service, table_id):
    return service.view(OPENER, table_id.value, NOBODY_CONNECTED).version


class Held:
    """A guard that holds the freeing inside the table's row lock until the test lets it go."""

    def __init__(self, absent=ABSENT):
        self.entered = threading.Event()
        self.go_on = threading.Event()
        self._absent = absent

    @contextmanager
    def guard(self):
        self.entered.set()
        assert self.go_on.wait(STEP_SECONDS * 4)
        yield self._absent


@contextmanager
def unknown_presence():
    raise PresenceUnknownError
    yield  # pragma: no cover - the guard raises before it yields


@pytest.fixture
def table_id(service):
    return undealt_table(service, "held")


class TestALeave:
    @pytest.mark.parametrize("newest_wins", [True, False], ids=["a leave", "a lapse where no hold exists"])
    def test_a_leave_and_a_lapse_where_no_hold_exists_store_a_deadline_one_hold_from_now(
        self, service, engine, table_id, newest_wins
    ):
        service.note_leave(table_id, LEAVER.account_id, HOLD_SECONDS, newest_wins=newest_wins)

        assert HOLD_SECONDS - STEP_SECONDS < seconds_left(engine, table_id, LEAVER.account_id) <= HOLD_SECONDS

    def test_a_newer_leave_replaces_the_older_deadline(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -10)

        service.note_leave(table_id, LEAVER.account_id, HOLD_SECONDS, newest_wins=True)

        assert seconds_left(engine, table_id, LEAVER.account_id) > HOLD_SECONDS - STEP_SECONDS
        assert holds(engine) == {(table_id.value, LEAVER.account_id)}

    def test_a_lapse_keeps_the_deadline_of_an_existing_hold(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, 10)
        before = rows_of(engine, table_id.value)["chair_holds"]

        service.note_leave(table_id, LEAVER.account_id, HOLD_SECONDS, newest_wins=False)

        assert rows_of(engine, table_id.value)["chair_holds"] == before

    def test_a_leave_of_an_account_without_a_chair_at_the_live_table_stores_nothing(
        self, service, engine, transactions, table_id
    ):
        ended = undealt_table(service, "ended")
        ended_at(transactions, ended)

        service.note_leave(table_id, SEATED[2].account_id, HOLD_SECONDS, newest_wins=True)
        service.note_leave(ended, LEAVER.account_id, HOLD_SECONDS, newest_wins=True)
        service.note_leave(TableId("0" * 32), LEAVER.account_id, HOLD_SECONDS, newest_wins=True)

        assert holds(engine) == set()


class TestAnArrival:
    def test_an_arrival_clears_the_hold(self, service, engine, table_id):
        service.note_leave(table_id, LEAVER.account_id, HOLD_SECONDS, newest_wins=True)

        service.clear_hold(table_id, LEAVER.account_id)

        assert holds(engine) == set()

    def test_an_arrival_during_a_freeing_waits_for_its_commit_and_finds_the_chair_free(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)
        held = Held()
        freeing = WorkInAThread(lambda: service.free_held_chair(table_id, LEAVER.account_id, held.guard()))
        freeing.start()
        assert held.entered.wait(STEP_SECONDS)
        arrival = WorkInAThread(lambda: service.clear_hold(table_id, LEAVER.account_id))
        arrival.start()

        wait_until_a_session_waits_for_a_lock(engine, arrival)
        held.go_on.set()
        freeing.join(STEP_SECONDS)
        arrival.join(STEP_SECONDS)

        assert freeing.outcome == [True]
        assert occupants(service, table_id) == ["Anna", None, None]
        assert holds(engine) == set()


class TestTheFreeing:
    def test_a_due_hold_of_an_absent_member_frees_the_chair_and_a_repeat_frees_nothing(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)
        version = version_of(service, table_id)

        freed = service.free_held_chair(table_id, LEAVER.account_id, nullcontext(ABSENT))
        again = service.free_held_chair(table_id, LEAVER.account_id, nullcontext(ABSENT))

        assert (freed, again) == (True, False)
        assert occupants(service, table_id) == ["Anna", None, None]
        assert version_of(service, table_id) == version + 1
        assert holds(engine) == set()

    def test_the_guard_is_left_once_the_freeing_is_committed(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)
        occupants_when_left = []

        @contextmanager
        def absent_until_left():
            yield ABSENT
            occupants_when_left.append(occupants(service, table_id))

        service.free_held_chair(table_id, LEAVER.account_id, absent_until_left())

        assert occupants_when_left == [["Anna", None, None]]

    def test_two_concurrent_freeings_of_one_hold_free_the_chair_once(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)
        version = version_of(service, table_id)
        held = Held()
        first = WorkInAThread(lambda: service.free_held_chair(table_id, LEAVER.account_id, held.guard()))
        first.start()
        assert held.entered.wait(STEP_SECONDS)
        second = WorkInAThread(lambda: service.free_held_chair(table_id, LEAVER.account_id, nullcontext(ABSENT)))
        second.start()

        wait_until_a_session_waits_for_a_lock(engine, second)
        held.go_on.set()
        first.join(STEP_SECONDS)
        second.join(STEP_SECONDS)

        assert (first.outcome, second.outcome) == ([True], [False])
        assert version_of(service, table_id) == version + 1

    def test_a_leave_written_during_a_freeing_leaves_the_chair_held_by_the_newer_deadline(
        self, service, engine, transactions, table_id
    ):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)
        freeing = WorkInAThread(lambda: service.free_held_chair(table_id, LEAVER.account_id, nullcontext(ABSENT)))

        with transactions.begin() as leaving:
            leaving.store_leave(table_id, LEAVER.account_id, HOLD_SECONDS, newest_wins=True)
            freeing.start()
            wait_until_a_session_waits_for_a_lock(engine, freeing)
        freeing.join(STEP_SECONDS)

        assert freeing.outcome == [False]
        assert occupants(service, table_id) == ["Anna", "Ben", None]
        assert seconds_left(engine, table_id, LEAVER.account_id) > HOLD_SECONDS - STEP_SECONDS

    def test_a_hold_not_yet_due_frees_nothing_and_stays(self, service, engine, table_id):
        service.note_leave(table_id, LEAVER.account_id, HOLD_SECONDS, newest_wins=True)

        assert service.free_held_chair(table_id, LEAVER.account_id, nullcontext(ABSENT)) is False
        assert occupants(service, table_id) == ["Anna", "Ben", None]
        assert holds(engine) == {(table_id.value, LEAVER.account_id)}

    def test_a_due_hold_of_a_present_member_keeps_the_chair_and_is_dropped(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)

        assert service.free_held_chair(table_id, LEAVER.account_id, nullcontext(PRESENT)) is False
        assert occupants(service, table_id) == ["Anna", "Ben", None]
        assert holds(engine) == set()

    def test_an_unknown_presence_frees_nothing_and_keeps_the_hold(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)

        presence = unknown_presence()

        with pytest.raises(PresenceUnknownError):
            service.free_held_chair(table_id, LEAVER.account_id, presence)

        assert occupants(service, table_id) == ["Anna", "Ben", None]
        assert holds(engine) == {(table_id.value, LEAVER.account_id)}

    def test_a_stopped_presence_frees_nothing_and_keeps_the_hold(self, service, engine, table_id):
        hold_due_in(engine, table_id, LEAVER.account_id, -1)

        assert service.free_held_chair(table_id, LEAVER.account_id, nullcontext(STOPPED)) is False
        assert occupants(service, table_id) == ["Anna", "Ben", None]
        assert holds(engine) == {(table_id.value, LEAVER.account_id)}

    def test_a_due_hold_at_a_dealt_table_frees_nothing_and_is_dropped(self, service, engine):
        dealt = seated_table(service, "dealt")
        hold_due_in(engine, dealt, LEAVER.account_id, -1)

        assert service.free_held_chair(dealt, LEAVER.account_id, nullcontext(ABSENT)) is False
        assert occupants(service, dealt) == ["Anna", "Ben", "Cleo"]
        assert holds(engine) == set()

    def test_a_due_hold_at_an_ended_table_is_dropped(self, service, engine, transactions, table_id):
        ended_at(transactions, table_id)
        hold_due_in(engine, table_id, LEAVER.account_id, -1)

        assert service.free_held_chair(table_id, LEAVER.account_id, nullcontext(ABSENT)) is False
        assert holds(engine) == set()

    def test_the_due_holds_are_those_whose_deadline_passed_the_oldest_first(self, service, engine, table_id):
        other = undealt_table(service, "other")
        hold_due_in(engine, table_id, LEAVER.account_id, -1)
        hold_due_in(engine, other, OPENER.account_id, -5)
        service.note_leave(other, LEAVER.account_id, HOLD_SECONDS, newest_wins=True)

        assert [(due.table_id, due.account_id) for due in service.due_holds()] == [
            (other, OPENER.account_id),
            (table_id, LEAVER.account_id),
        ]


def test_forgetting_an_ended_table_drops_its_holds(service, engine, transactions, table_id):
    ended_at(transactions, table_id)
    hold_due_in(engine, table_id, LEAVER.account_id, HOLD_SECONDS)
    with transactions.begin() as transaction:
        transaction.forget_ended_before(ENDED_AT)

    assert holds(engine) == set()


def test_the_lobby_shows_the_whole_seconds_left_of_a_stored_hold_rounded_up(service, engine, table_id):
    hold_due_in(engine, table_id, LEAVER.account_id, 90.9)
    before = seconds_left(engine, table_id, LEAVER.account_id)

    (entry,) = service.my_tables(OPENER.account_id, [table_id], {table_id.value: frozenset({OPENER.account_id})}, 7)
    after = seconds_left(engine, table_id, LEAVER.account_id)

    shown = [chair.hold_seconds_left for chair in entry.chairs]
    assert shown[0] is None
    assert shown[2] is None
    # Rounded up, the whole seconds shown at the read are at least the exact seconds left then, and less than one more.
    assert isinstance(shown[1], int)
    assert after <= shown[1] < before + 1
