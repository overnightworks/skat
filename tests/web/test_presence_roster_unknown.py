"""A roster that cannot be read, or cannot yet vouch for an absence, frees, ends and notes nothing, and each of those
tries again; a deal, which acts on who is listed, tries again when the read fails.
"""

import asyncio
import threading

import pytest

from skat.web import presence as presence_module
from skat.web.presence import HOLD_SWEEP_EVERY_SECONDS, PAUSE_SWEEP_EVERY_SECONDS
from skat.web.presence_line import PresenceTimer
from tests.support.log_lines import logged
from tests.web.support.presence import OTHER_TABLE, TABLE, connect, failed_timers, run, stop_during_a_hanging_read

UNREACHABLE = ConnectionError("redis is unreachable")


class TestTheEndOfAnEmptyTable:
    def test_ends_nothing_while_the_roster_cannot_be_read_and_tries_again(self, holding, leases, time, ends, capsys):
        ends.due_now = [TABLE]
        holding.start_sweeps()
        leases.reading_fails = [UNREACHABLE]

        with logged(capsys) as lines:
            run(time.advance(HOLD_SWEEP_EVERY_SECONDS))
        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert failed_timers(lines) == [(PresenceTimer.EMPTY_TABLE_END, "warning")]
        assert ends.calls == [(TABLE, frozenset())]

    def test_ends_nothing_while_the_roster_is_unsettled_and_lists_nobody_at_the_table(
        self, holding, leases, time, ends
    ):
        ends.due_now = [TABLE]
        holding.start_sweeps()
        leases.settled = False

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert ends.calls == []

    def test_reads_who_is_listed_while_the_roster_is_unsettled(self, holding, elsewhere, leases, time, ends):
        ends.due_now = [TABLE]
        holding.start_sweeps()
        connect(elsewhere, TABLE, "anna", lambda: None)
        leases.settled = False

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert ends.calls == [(TABLE, {"anna"})]


class TestTheNextDeal:
    def test_stores_the_deal_as_due_now_when_the_roster_cannot_be_read_and_the_next_sweep_deals(
        self, holding, leases, time, deals, capsys
    ):
        connect(holding, TABLE, "anna", lambda: None)
        leases.reading_fails = [UNREACHABLE]

        with logged(capsys) as lines:
            run(holding.deal_now(TABLE))
        assert (deals.calls, deals.deferred) == ([], [TABLE])
        assert failed_timers(lines) == [(PresenceTimer.NEXT_DEAL, "warning")]

        deals.due_now = [TABLE]
        holding.start_sweeps()
        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))
        assert deals.calls == [(TABLE, {"anna"})]

    def test_a_due_pause_stays_while_the_roster_is_unsettled_and_misses_someone_seated_and_deals_once_it_lists_all(
        self, holding, elsewhere, leases, time, deals
    ):
        deals.seated = frozenset({"anna", "ben"})
        deals.due_now = [TABLE]
        holding.start_sweeps()
        connect(elsewhere, TABLE, "anna", lambda: None)
        leases.settled = False

        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))
        assert (deals.calls, deals.due_now) == ([], [TABLE])

        connect(elsewhere, TABLE, "ben", lambda: None)
        leases.settled = True
        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))
        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))

        assert (deals.calls, deals.due_now) == ([(TABLE, {"anna", "ben"})], [])

    def test_a_due_pause_the_unsettled_roster_cannot_vouch_for_does_not_hold_back_a_later_due_table(
        self, holding, elsewhere, leases, time, deals
    ):
        deals.seated_at = {TABLE: frozenset({"anna", "ben"}), OTHER_TABLE: frozenset({"cem"})}
        deals.due_now = [TABLE, OTHER_TABLE]
        holding.start_sweeps()
        connect(elsewhere, TABLE, "anna", lambda: None)
        connect(elsewhere, OTHER_TABLE, "cem", lambda: None)
        leases.settled = False

        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))

        assert (deals.calls, deals.due_now) == ([(OTHER_TABLE, {"cem"})], [TABLE])

    def test_a_due_pause_is_dropped_without_a_deal_once_the_roster_settles_without_someone_seated(
        self, holding, elsewhere, leases, time, deals, wakes
    ):
        deals.seated = frozenset({"anna", "ben"})
        deals.due_now = [TABLE]
        holding.start_sweeps()
        connect(elsewhere, TABLE, "anna", wakes.callback("anna"))
        leases.settled = False
        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))
        before = wakes.counts["anna"]

        leases.settled = True
        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))

        assert (deals.calls, deals.due_now, wakes.counts["anna"]) == ([(TABLE, {"anna"})], [], before)

    def test_a_due_pause_counts_a_seated_agent_whose_lease_runs_on_this_pod_as_listed(
        self, holding, leases, time, deals
    ):
        deals.seated = frozenset({"agent"})
        deals.due_now = [TABLE]
        holding.start_sweeps()
        holding.renew_lease("agent")
        leases.settled = False

        run(time.advance(PAUSE_SWEEP_EVERY_SECONDS))

        assert (deals.calls, deals.due_now) == ([(TABLE, frozenset())], [])

    def test_acts_on_the_holders_an_unsettled_roster_lists_even_when_it_lists_nobody(self, holding, leases, deals):
        leases.settled = False

        run(holding.deal_now(TABLE))

        assert deals.calls == [(TABLE, frozenset())]

    def test_stores_the_deal_as_due_now_even_when_the_presence_stops_while_the_failing_deal_is_in_flight(
        self, holding, time, deals
    ):
        async def stop_then_fail():
            holding.stop()
            raise UNREACHABLE

        deals.meanwhile = stop_then_fail

        run(holding.deal_now(TABLE))

        assert (time.pending, deals.deferred) == (0, [TABLE])


class TestAStalledRoster:
    def test_counts_as_unknown_after_its_timeout_and_frees_nothing(
        self, holding, leases, time, holds, monkeypatch, capsys
    ):
        monkeypatch.setattr(presence_module, "ROSTER_READ_TIMEOUT_SECONDS", 0.05)
        holds.due_now = [(TABLE, "anna")]
        leases.reading_hangs = True

        with logged(capsys) as lines:
            holding.start_sweeps()
            run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert holds.outcomes == []
        assert failed_timers(lines) == [(PresenceTimer.CHAIR_RELEASE, "warning")]

    def test_a_stop_ends_a_read_in_flight_and_the_guard_yields_nobody_at_once(
        self, holding, leases, deals, monkeypatch
    ):
        monkeypatch.setattr(presence_module, "ROSTER_READ_TIMEOUT_SECONDS", 30)

        stop_during_a_hanging_read(holding, leases, lambda: holding.deal_now(TABLE))

        assert deals.calls == [(TABLE, None)]

    def test_a_presence_stopped_before_a_deal_reads_no_roster_and_the_guard_yields_nobody(self, holding, leases, deals):
        holding.stop()

        run(holding.deal_now(TABLE))

        assert (deals.calls, leases.live_read_count) == ([(TABLE, None)], 0)

    def test_a_roster_read_for_a_worker_is_made_on_the_event_loop_which_a_waiting_worker_leaves_free(
        self, holding, leases, time, deals
    ):
        async def scenario():
            loop_thread = threading.get_ident()
            await holding.deal_now(TABLE)
            return loop_thread

        loop_thread = run(scenario())

        assert (deals.calls, set(leases.read_threads)) == ([(TABLE, frozenset())], {loop_thread})


class TestTheCloseOfAStream:
    def test_ends_its_lease_and_stores_the_leave_though_the_closing_task_is_cancelled_meanwhile(
        self, holding, leases, holds
    ):
        async def scenario():
            subscription = await holding.subscribe(TABLE, "anna", lambda: None)
            leases.ending_gate = asyncio.Event()
            closing = asyncio.create_task(holding.close(subscription))
            await asyncio.sleep(0)
            closing.cancel()
            await asyncio.sleep(0)
            leases.ending_gate.set()
            with pytest.raises(asyncio.CancelledError):
                await closing

        run(scenario())

        assert (leases.holders, holds.left) == ([], [(TABLE, "anna")])

    def test_closing_twice_changes_nothing_the_second_time(self, holding, wakes, time):
        connect(holding, TABLE, "ben", lambda: None)
        subscription = connect(holding, TABLE, "anna", wakes.callback("anna"))
        run(holding.close(subscription))
        pending = time.pending

        run(holding.close(subscription))

        assert time.pending == pending


class TestAnArrival:
    def test_wakes_the_other_streams_though_the_roster_cannot_be_read(self, holding, leases, wakes):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        before = wakes.counts["ben"]
        leases.reading_fails = [UNREACHABLE]

        connect(holding, TABLE, "anna", wakes.callback("anna"))

        assert wakes.counts["ben"] == before + 1

    def test_fails_when_its_lease_cannot_start_and_leaves_nothing_registered(self, holding, leases, wakes):
        leases.starting_fails = [UNREACHABLE]
        wake_anna = wakes.callback("anna")

        with pytest.raises(ConnectionError):
            connect(holding, TABLE, "anna", wake_anna)

        holding.wake_table(TABLE)
        assert wakes.counts == {"anna": 0}
