"""The presence's timers write one `presence_timer.ended` line for the first run of a streak that failed and one for
the run that ends it, and none for a run that succeeds with no streak behind it.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from agents.member import LEASE_SECONDS
from logline import Outcome

from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    NEXT_DEAL_PAUSE_SECONDS,
    AgentLease,
    ChairHold,
    EmptyTable,
    NextDeal,
    Presence,
)
from skat.web.presence_line import EVENT, PresenceTimer
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.idle_presence import idle_wakes
from tests.support.in_memory_leases import InMemoryLeases
from tests.support.log_lines import lines_of, logged
from tests.web.support.presence import FAILURE_NAMING_AN_ACCOUNT, HOLD_SECONDS, TABLE, Notes, connect, run

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
    releases: Any


@pytest.fixture
def timers(time, releases, deals, ends):
    leases, notes, roster = Leases(), Notes(), InMemoryLeases()
    presence = Presence(
        ChairHold(HOLD_SECONDS, time.clock, time, releases.free_chair),
        NextDeal(NEXT_DEAL_PAUSE_SECONDS, deals.deal_next),
        EmptyTable(DEFAULT_EMPTY_TABLE_SECONDS, ends.end, notes.note),
        AgentLease(LEASE_SECONDS, leases.seated_tables),
        idle_wakes(),
        roster,
    )
    return Timers(presence, time, leases, roster, notes, ends, deals, releases)


def fail_the_next_runs(world, timer, count):
    store = {
        PresenceTimer.LEASE_SETTLE: world.leases,
        PresenceTimer.NEXT_DEAL: world.deals,
        PresenceTimer.EMPTY_SINCE_WRITE: world.notes,
        PresenceTimer.EMPTY_TABLE_END: world.ends,
        PresenceTimer.CHAIR_RELEASE: world.releases,
    }[timer]
    store.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT) for _ in range(count)]


def first_run(world, timer, leaving):
    presence, time = world.presence, world.time
    if timer is PresenceTimer.LEASE_SETTLE:
        presence.renew_lease(MEMBER)
        run(time.advance(0))
    elif timer is PresenceTimer.NEXT_DEAL:
        run(presence.deal_now(TABLE))
    elif timer is PresenceTimer.EMPTY_SINCE_WRITE:
        run(presence.close(leaving))
        run(time.advance(0))
    elif timer is PresenceTimer.EMPTY_TABLE_END:
        presence.watch_empty_table(TABLE)
        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))
    else:
        run(presence.close(leaving))
        run(time.advance(HOLD_SECONDS))


def next_run(world, timer):
    if timer is PresenceTimer.NEXT_DEAL:
        run(world.presence.deal_now(TABLE))
    else:
        run(world.time.advance(CHAIR_RELEASE_RETRY_SECONDS))


def started(world, timer, failures):
    """Starts the timer's first run with the next `failures` runs failing, as it would be on a table."""
    leaving = None
    if timer in (PresenceTimer.EMPTY_SINCE_WRITE, PresenceTimer.CHAIR_RELEASE):
        leaving = connect(world.presence, TABLE, MEMBER, lambda: None)
    fail_the_next_runs(world, timer, failures)
    first_run(world, timer, leaving)


# The close's absence check shares the roster with the note of who is present, so its test makes the roster's outage
# outlast both rather than fail a count of runs.
TIMERS = [timer for timer in PresenceTimer if timer is not PresenceTimer.CLOSE_ABSENCE_CHECK]


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
    def test_a_timer_that_succeeds_with_no_streak_behind_it_writes_no_line(self, timers, capsys, timer):
        with logged(capsys) as lines:
            started(timers, timer, 0)

        assert lines_of(lines, EVENT) == []

    @pytest.mark.parametrize("timer", [timer for timer in TIMERS if timer is not PresenceTimer.LEASE_SETTLE])
    def test_a_timers_line_names_its_table(self, timers, capsys, timer):
        with logged(capsys) as lines:
            started(timers, timer, 1)

        (line,) = lines_of(lines, EVENT)
        assert line["table_id"] == TABLE


class TestTheCloseAbsenceCheckLine:
    def test_a_roster_that_cannot_be_read_writes_one_streak_instead_of_an_error_per_retry(self, timers, capsys):
        leaving = connect(timers.presence, TABLE, MEMBER, lambda: None)
        timers.roster.reading_fails = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)] * 100

        with logged(capsys) as lines:
            run(timers.presence.close(leaving))
            run(timers.time.advance(CHAIR_RELEASE_RETRY_SECONDS))
            run(timers.time.advance(CHAIR_RELEASE_RETRY_SECONDS))
            timers.roster.reading_fails.clear()
            run(timers.time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        first, recovery = [
            line for line in lines_of(lines, EVENT) if line["timer"] == PresenceTimer.CLOSE_ABSENCE_CHECK
        ]
        assert (first["outcome"], first["failed_run_count"], first["table_id"]) == (Outcome.FAILED, 1, TABLE)
        assert (recovery["outcome"], recovery["failed_run_count"]) == (Outcome.OK, 3)
        assert lines_of(lines, "stream_close.failed") == []
        assert MEMBER not in str(lines_of(lines, EVENT))
