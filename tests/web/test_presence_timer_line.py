"""The presence's timers write one `presence_timer.ended` line for the first run of a streak that failed and one for
the run that ends it, and none for a run that succeeds with no streak behind it.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from agents.member import LEASE_SECONDS
from logline import Outcome

from skat.web.end_answers import EndAnswers
from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    HOLD_SWEEP_EVERY_SECONDS,
    PAUSE_SWEEP_EVERY_SECONDS,
    AgentLease,
    EmptyTable,
    Presence,
)
from skat.web.presence_line import EVENT, PresenceTimer
from tests.support.idle_presence import idle_wakes
from tests.support.in_memory_leases import InMemoryLeases
from tests.support.log_lines import lines_of, logged
from tests.web.support.presence import FAILURE_NAMING_AN_ACCOUNT, TABLE, Notes, chair_hold, connect, run

MEMBER = "anna"


class Leases:
    """The read of an agent's tables as the presence calls it: it raises what `failures` holds, then answers none."""

    def __init__(self):
        self.failures = []

    async def seated_tables(self, account_id):
        if self.failures:
            raise self.failures.pop(0)
        return []


@dataclass
class Timers:
    presence: Presence
    time: Any
    leases: Leases
    roster: InMemoryLeases
    notes: Notes
    ends: Any
    deals: Any
    holds: Any
    lapses: Any


@pytest.fixture
def timers(time, holds, deals, ends, lapses):
    leases, notes, roster = Leases(), Notes(), InMemoryLeases()
    presence = Presence(
        chair_hold(time, holds),
        deals.port(),
        EmptyTable(ends.end, notes.note, ends.due),
        AgentLease(LEASE_SECONDS, leases.seated_tables),
        idle_wakes(),
        roster,
        EndAnswers(lapses.lapse),
    )
    return Timers(presence, time, leases, roster, notes, ends, deals, holds, lapses)


def fail_the_next_runs(world, timer, count):
    store, failures = {
        PresenceTimer.LEASE_SETTLE: (world.leases, "failures"),
        PresenceTimer.NEXT_DEAL: (world.deals, "failures"),
        PresenceTimer.NEXT_DEAL_WRITE: (world.deals, "write_failures"),
        PresenceTimer.PAUSE_SWEEP: (world.deals, "due_failures"),
        PresenceTimer.EMPTY_SINCE_WRITE: (world.notes, "failures"),
        PresenceTimer.EMPTY_TABLE_END: (world.ends, "failures"),
        PresenceTimer.EMPTY_SWEEP: (world.ends, "due_failures"),
        PresenceTimer.CHAIR_RELEASE: (world.holds, "free_failures"),
        PresenceTimer.HOLD_SWEEP: (world.holds, "due_failures"),
        PresenceTimer.LEAVE_WRITE: (world.holds, "leave_failures"),
        PresenceTimer.HOLD_CLEAR: (world.holds, "clear_failures"),
        PresenceTimer.END_ANSWER_LAPSE: (world.lapses, "failures"),
    }[timer]
    setattr(store, failures, [ConnectionError(FAILURE_NAMING_AN_ACCOUNT) for _ in range(count)])


def first_run(world, timer, leaving):
    presence, time = world.presence, world.time
    if timer is PresenceTimer.LEASE_SETTLE:
        presence.renew_lease(MEMBER)
        run(time.advance(0))
    elif timer is PresenceTimer.NEXT_DEAL:
        run(presence.deal_now(TABLE))
    elif timer is PresenceTimer.NEXT_DEAL_WRITE:
        run(presence.deal_soon(TABLE))
    elif timer is PresenceTimer.PAUSE_SWEEP:
        presence.start_sweeps()
        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))
    elif timer in (PresenceTimer.EMPTY_SINCE_WRITE, PresenceTimer.LEAVE_WRITE):
        run(presence.close(leaving))
        run(time.advance(0))
    elif timer in (PresenceTimer.EMPTY_TABLE_END, PresenceTimer.EMPTY_SWEEP):
        world.ends.due_now = [TABLE]
        presence.start_sweeps()
        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))
    elif timer is PresenceTimer.HOLD_CLEAR:
        connect(presence, TABLE, MEMBER, lambda: None)
    elif timer is PresenceTimer.END_ANSWER_LAPSE:
        presence.end_answer_watch.watch(TABLE, 0)
        run(time.advance(0))
    else:
        world.holds.due_now = [(TABLE, MEMBER)]
        presence.start_sweeps()
        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))


def next_run(world, timer):
    if timer is PresenceTimer.NEXT_DEAL:
        run(world.presence.deal_now(TABLE))
    elif timer is PresenceTimer.NEXT_DEAL_WRITE:
        run(world.presence.deal_soon(TABLE))
    elif timer is PresenceTimer.HOLD_CLEAR:
        connect(world.presence, TABLE, MEMBER, lambda: None)
    elif timer is PresenceTimer.PAUSE_SWEEP:
        run(world.time.advance(PAUSE_SWEEP_EVERY_SECONDS))
    elif timer in (
        PresenceTimer.CHAIR_RELEASE,
        PresenceTimer.HOLD_SWEEP,
        PresenceTimer.EMPTY_TABLE_END,
        PresenceTimer.EMPTY_SWEEP,
    ):
        run(world.time.advance(HOLD_SWEEP_EVERY_SECONDS))
    else:
        run(world.time.advance(CHAIR_RELEASE_RETRY_SECONDS))


def started(world, timer, failures):
    """Starts the timer's first run with the next `failures` runs failing, as it would be on a table."""
    leaving = None
    if timer in (PresenceTimer.EMPTY_SINCE_WRITE, PresenceTimer.LEAVE_WRITE):
        leaving = connect(world.presence, TABLE, MEMBER, lambda: None)
    fail_the_next_runs(world, timer, failures)
    first_run(world, timer, leaving)


TIMERS = list(PresenceTimer)
SWEEP_TIMERS = (PresenceTimer.HOLD_SWEEP, PresenceTimer.PAUSE_SWEEP, PresenceTimer.EMPTY_SWEEP)


class TestThePresenceTimerLine:
    @pytest.mark.parametrize("timer", TIMERS)
    def test_a_timer_that_keeps_failing_writes_its_first_failure_and_its_recovery_with_the_runs_that_failed(
        self, timers, capsys, timer
    ):
        with logged(capsys) as lines:
            started(timers, timer, 3)
            next_run(timers, timer)
            next_run(timers, timer)
            next_run(timers, timer)

        first, recovery = lines_of(lines, EVENT)
        assert (first["timer"], first["outcome"], first["level"], first["failed_run_count"]) == (
            timer,
            Outcome.FAILED,
            "warning",
            1,
        )
        assert (recovery["timer"], recovery["outcome"], recovery["level"], recovery["failed_run_count"]) == (
            timer,
            Outcome.OK,
            "info",
            3,
        )
        assert MEMBER not in str(lines_of(lines, EVENT))

    @pytest.mark.parametrize("timer", TIMERS)
    def test_a_timer_that_keeps_failing_writes_no_error_line_per_retry(self, timers, capsys, timer):
        with logged(capsys) as lines:
            started(timers, timer, 3)
            next_run(timers, timer)
            next_run(timers, timer)

        assert [line for line in lines if line["level"] == "error"] == []

    @pytest.mark.parametrize("timer", TIMERS)
    def test_a_timer_that_succeeds_with_no_streak_behind_it_writes_no_line(self, timers, capsys, timer):
        with logged(capsys) as lines:
            started(timers, timer, 0)

        assert lines_of(lines, EVENT) == []

    @pytest.mark.parametrize(
        "timer", [timer for timer in TIMERS if timer not in (PresenceTimer.LEASE_SETTLE, *SWEEP_TIMERS)]
    )
    def test_a_timers_line_names_its_table(self, timers, capsys, timer):
        with logged(capsys) as lines:
            started(timers, timer, 1)

        (line,) = lines_of(lines, EVENT)
        assert line["table_id"] == TABLE
