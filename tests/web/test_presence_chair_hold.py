"""The presence's part of a chair hold: it stores a leave while the leaving stream still counts, clears the hold at an
arrival, and sweeps the due holds with a guard that frees only an account the roster vouches is gone.
"""

import asyncio

import pytest
from agents.member import LEASE_SECONDS
from tandem import Lapse
from tandem.deadlines import Due

from skat.web import presence as presence_module
from skat.web.presence import CHAIR_RELEASE_RETRY_SECONDS, HOLD_SWEEP_EVERY_SECONDS, AgentLease, Presence
from skat.web.presence_line import EVENT, PresenceTimer
from skat.web.stream_holder import StreamHolder
from tests.support.idle_presence import idle_agent_lease, idle_empty_table, idle_next_deal, idle_wakes
from tests.support.log_lines import lines_of, logged
from tests.web.support.presence import (
    OTHER_TABLE,
    TABLE,
    chair_hold,
    connect,
    failed_timers,
    run,
    stop_during_a_hanging_read,
)

UNREACHABLE = ConnectionError("redis is unreachable")


def error_types(lines, timer):
    return [line.get("error_type") for line in lines_of(lines, EVENT) if line["timer"] == timer]


def sweep(holding, time):
    """Start the sweeps and run the first."""
    holding.start_hold_sweeps()
    run(time.advance(HOLD_SWEEP_EVERY_SECONDS))


def lapse_of(table_id, account_id):
    return Lapse(StreamHolder(table_id, account_id, "stream").encoded(), "generation", Due("key", "claim"))


def streams_on_another_pod(holding, elsewhere, account_id):
    connect(elsewhere, TABLE, account_id, lambda: None)


def holds_a_lease_here(holding, elsewhere, account_id):
    holding.renew_lease(account_id)


class TestTheFreeingGuard:
    @pytest.fixture
    def due(self, holds):
        holds.due_now = [(TABLE, "anna")]

    def test_the_freeing_guard_raises_presence_unknown_when_the_roster_cannot_be_read(
        self, holding, holds, leases, time, due, capsys
    ):
        leases.reading_fails = [UNREACHABLE]

        with logged(capsys) as lines:
            sweep(holding, time)

        assert (holds.calls, holds.outcomes) == ([(TABLE, "anna")], [])
        assert failed_timers(lines) == [(PresenceTimer.CHAIR_RELEASE, "warning")]
        assert error_types(lines, PresenceTimer.CHAIR_RELEASE) == ["PresenceUnknownError"]

    def test_the_freeing_guard_raises_presence_unknown_when_the_roster_is_unsettled_and_does_not_list_the_account(
        self, holding, holds, leases, time, due
    ):
        leases.settled = False

        sweep(holding, time)

        assert (holds.calls, holds.outcomes) == ([(TABLE, "anna")], [])

    def test_the_freeing_guard_yields_false_when_the_roster_lists_the_account(
        self, holding, holds, elsewhere, leases, time, due
    ):
        leases.settled = False
        connect(elsewhere, TABLE, "anna", lambda: None)

        sweep(holding, time)

        assert holds.outcomes == [False]

    def test_the_freeing_guard_yields_false_while_an_agent_lease_of_the_account_runs_on_this_pod(
        self, holding, holds, time, due
    ):
        holding.renew_lease("anna")

        sweep(holding, time)

        assert holds.outcomes == [False]

    def test_the_freeing_guard_yields_none_once_the_presence_stopped_and_nothing_is_written(
        self, holding, holds, leases, time, due, monkeypatch
    ):
        monkeypatch.setattr(presence_module, "ROSTER_READ_TIMEOUT_SECONDS", 30)
        holding.start_hold_sweeps()

        stop_during_a_hanging_read(holding, leases, lambda: time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert (holds.outcomes, holds.due_now) == ([None], [(TABLE, "anna")])

    def test_the_freeing_guard_yields_true_when_the_settled_roster_does_not_list_the_account(
        self, holding, holds, time, due
    ):
        sweep(holding, time)

        assert holds.outcomes == [True]


class TestALeave:
    def test_a_last_stream_ending_stores_its_leave_while_its_lease_still_counts_it(self, holding, holds):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        counted_at_the_leave = []

        async def note_who_counts():
            counted_at_the_leave.append(await holding.connected(TABLE))

        holds.on_leave = note_who_counts

        run(holding.close(subscription))

        assert (holds.left, counted_at_the_leave) == ([(TABLE, "anna")], [{"anna"}])
        assert run(holding.connected(TABLE)) == frozenset()

    def test_a_stream_ending_while_the_server_stops_still_stores_its_leave(self, holding, holds, leases):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        holding.stop()

        run(holding.close(subscription))

        assert (holds.left, leases.holders) == ([(TABLE, "anna")], [])

    def test_a_second_stream_of_the_account_on_this_pod_ending_stores_no_leave(self, holding, holds):
        connect(holding, TABLE, "anna", lambda: None)
        second = connect(holding, TABLE, "anna", lambda: None)

        run(holding.close(second))

        assert holds.left == []

    def test_a_stream_ending_while_the_account_streams_on_another_pod_stores_its_leave_only_at_the_last_stream(
        self, holding, holds, leases, time
    ):
        other_pod = Presence(
            chair_hold(time, holds), idle_next_deal(), idle_empty_table(), idle_agent_lease(), idle_wakes(), leases
        )
        here = connect(holding, TABLE, "anna", lambda: None)
        there = connect(other_pod, TABLE, "anna", lambda: None)

        run(holding.close(here))
        assert holds.left == []

        run(other_pod.close(there))
        assert holds.left == [(TABLE, "anna")]

    def test_a_stream_ending_while_the_roster_cannot_be_read_stores_its_leave_and_ends_its_lease(
        self, holding, holds, leases
    ):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        leases.reading_fails = [UNREACHABLE]

        run(holding.close(subscription))

        assert (holds.left, leases.holders) == ([(TABLE, "anna")], [])

    def test_a_leave_that_cannot_be_stored_is_logged_as_leave_write_and_stored_on_the_retry(
        self, holding, holds, leases, time, capsys
    ):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        holds.leave_failures = [UNREACHABLE]

        with logged(capsys) as lines:
            run(holding.close(subscription))
        assert (holds.left, leases.holders) == ([], [])
        assert failed_timers(lines) == [(PresenceTimer.LEAVE_WRITE, "warning")]
        assert error_types(lines, PresenceTimer.LEAVE_WRITE) == ["ConnectionError"]

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert holds.left == [(TABLE, "anna")]

    def test_a_leave_retry_stores_nothing_once_the_account_streams_again(self, holding, holds, elsewhere, time):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        holds.leave_failures = [UNREACHABLE]
        run(holding.close(subscription))
        connect(elsewhere, TABLE, "anna", lambda: None)

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert holds.left == []

    def test_a_leave_that_fails_while_the_server_stops_is_not_retried_and_releases_the_lease(
        self, holding, holds, leases, time
    ):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        holding.stop()
        holds.leave_failures = [UNREACHABLE]

        run(holding.close(subscription))

        assert (holds.left, leases.holders, time.pending) == ([], [], 0)

    def test_a_lapsed_stream_stores_its_leave_as_a_lapse_and_wakes_its_table(self, holding, holds, leases, wakes):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        before = wakes.counts["ben"]
        leases.lapses = [lapse_of(TABLE, "anna")]

        run(self.served(holding, leases))

        assert (holds.lapsed, holds.left) == ([(TABLE, "anna")], [])
        assert wakes.counts["ben"] == before + 1

    @pytest.mark.parametrize("back", [streams_on_another_pod, holds_a_lease_here])
    def test_a_lapse_of_an_account_that_is_still_here_stores_no_leave(self, holding, holds, elsewhere, leases, back):
        back(holding, elsewhere, "anna")
        leases.lapses = [lapse_of(TABLE, "anna")]

        run(self.served(holding, leases))

        assert (holds.lapsed, holds.left) == ([], [])

    def test_a_lapse_whose_leave_fails_raises_so_it_is_handed_again(self, holding, holds, leases):
        holds.leave_failures = [UNREACHABLE]
        leases.lapses = [lapse_of(TABLE, "anna")]

        run(self.served(holding, leases))

        assert (leases.handler_failures, holds.lapsed) == ([UNREACHABLE], [(TABLE, "anna")])

    def test_an_agent_lease_that_lapses_stores_its_leave_as_a_lapse_at_every_table_it_sits_at(
        self, holds, leases, time
    ):
        presence = self.agent_seated_at_both(holds, leases, time)
        presence.renew_lease("agent")
        run(time.advance(0))
        assert holds.lapsed == []

        run(time.advance(LEASE_SECONDS))

        assert (holds.lapsed, holds.left) == ([(TABLE, "agent"), (OTHER_TABLE, "agent")], [])

    def test_an_agent_lapse_whose_leave_fails_stores_it_as_a_lapse_on_the_retry(self, holds, leases, time):
        presence = self.agent_seated_at_both(holds, leases, time)
        presence.renew_lease("agent")
        run(time.advance(0))
        holds.leave_failures = [UNREACHABLE]

        run(time.advance(LEASE_SECONDS))
        assert holds.lapsed == [(OTHER_TABLE, "agent")]
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert (holds.lapsed, holds.left) == ([(OTHER_TABLE, "agent"), (TABLE, "agent")], [])

    @staticmethod
    def agent_seated_at_both(holds, leases, time):
        async def seated_at_both(account_id):
            return [TABLE, OTHER_TABLE]

        return Presence(
            chair_hold(time, holds),
            idle_next_deal(),
            idle_empty_table(),
            AgentLease(LEASE_SECONDS, seated_at_both),
            idle_wakes(),
            leases,
        )

    @staticmethod
    async def served(holding, leases):
        serving = asyncio.create_task(holding.serve_lapses())
        await asyncio.wait_for(leases.lapses_handed.wait(), 5)
        serving.cancel()
        await asyncio.gather(serving, return_exceptions=True)


class TestAnArrival:
    def test_an_arrival_clears_the_accounts_hold_after_its_lease_started(self, holding, holds):
        counted_at_the_clear = []

        async def note_who_counts():
            counted_at_the_clear.append(await holding.connected(TABLE))

        holds.on_clear = note_who_counts

        connect(holding, TABLE, "anna", lambda: None)

        assert (holds.cleared, counted_at_the_clear) == ([(TABLE, "anna")], [{"anna"}])

    def test_an_arrival_whose_hold_clear_fails_still_streams_and_logs_the_error_type(self, holding, holds, capsys):
        holds.clear_failures = [UNREACHABLE]

        with logged(capsys) as lines:
            connect(holding, TABLE, "anna", lambda: None)

        assert run(holding.connected(TABLE)) == {"anna"}
        assert failed_timers(lines) == [(PresenceTimer.HOLD_CLEAR, "warning")]
        assert error_types(lines, PresenceTimer.HOLD_CLEAR) == ["ConnectionError"]


class TestTheSweep:
    def test_the_sweep_frees_each_due_hold_and_wakes_only_tables_it_freed_at(
        self, holding, holds, elsewhere, wakes, time
    ):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        connect(holding, OTHER_TABLE, "cleo", wakes.callback("cleo"))
        connect(elsewhere, OTHER_TABLE, "dora", lambda: None)
        before = dict(wakes.counts)
        holds.due_now = [(TABLE, "anna"), (OTHER_TABLE, "dora")]

        sweep(holding, time)

        assert holds.outcomes == [True, False]
        assert wakes.counts == {"ben": before["ben"] + 1, "cleo": before["cleo"]}

    def test_a_due_hold_frees_nothing_while_the_roster_cannot_be_read_and_is_freed_at_a_later_sweep(
        self, holding, holds, leases, time, capsys
    ):
        holds.due_now = [(TABLE, "anna")]
        leases.reading_fails = [UNREACHABLE]

        with logged(capsys) as lines:
            sweep(holding, time)
            run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert holds.outcomes == [True]
        assert failed_timers(lines) == [(PresenceTimer.CHAIR_RELEASE, "warning")]

    def test_a_sweep_tick_stops_at_the_first_unknown_presence_and_the_next_tick_runs(
        self, holding, holds, leases, time
    ):
        holds.due_now = [(TABLE, "anna"), (OTHER_TABLE, "ben")]
        leases.reading_fails = [UNREACHABLE]

        sweep(holding, time)
        assert holds.calls == [(TABLE, "anna")]

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))
        assert holds.outcomes == [True, True]

    def test_a_failed_freeing_is_logged_with_its_error_type_and_tried_again_at_the_next_sweep(
        self, holding, holds, time, capsys
    ):
        holds.due_now = [(TABLE, "anna"), (OTHER_TABLE, "ben")]
        holds.free_failures = [UNREACHABLE]

        with logged(capsys) as lines:
            sweep(holding, time)
            assert holds.outcomes == [True]
            run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert holds.outcomes == [True, True]
        assert error_types(lines, PresenceTimer.CHAIR_RELEASE)[0] == "ConnectionError"

    def test_a_stopped_presence_sweeps_no_more(self, holding, holds, time):
        holding.start_hold_sweeps()
        holding.stop()
        holds.due_now = [(TABLE, "anna")]

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert (holds.calls, time.pending) == ([], 0)
