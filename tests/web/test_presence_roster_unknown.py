"""A roster that cannot be read, or cannot yet vouch for an absence, frees, ends and notes nothing, and each of those
tries again; a deal, which acts on who is listed, tries again when the read fails.
"""

import asyncio
import threading

import pytest
from structlog.testing import capture_logs

from skat.web import presence as presence_module
from skat.web.presence import CHAIR_RELEASE_RETRY_SECONDS
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.web.support.presence import HOLD_SECONDS, TABLE, connect, run

UNREACHABLE = ConnectionError("redis is unreachable")


def logged_failures(logs):
    return [(log["event"], log["error_type"]) for log in logs if log["log_level"] == "error"]


class TestAFreeingOfAChair:
    def test_reads_the_roster_again_under_the_row_lock_and_frees_nothing_while_it_cannot_be_read(
        self, holding, leases, time, releases
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        leases.reading_fails = [UNREACHABLE]

        with capture_logs() as logs:
            run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == []
        assert logged_failures(logs) == [("chair_release.failed", "PresenceUnknownError")]

    def test_frees_the_chair_on_the_retry_once_the_roster_can_be_read(self, holding, leases, time, releases):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        leases.reading_fails = [UNREACHABLE]
        run(time.advance(HOLD_SECONDS))

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert releases.outcomes == [True]

    def test_frees_nothing_while_the_roster_is_unsettled_and_does_not_list_the_account(
        self, holding, leases, time, releases
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        leases.settled = False

        run(time.advance(HOLD_SECONDS))
        assert releases.outcomes == []

        leases.settled = True
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert releases.outcomes == [True]

    def test_is_not_due_while_an_unsettled_roster_lists_the_account(self, holding, elsewhere, leases, time, releases):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        leases.settled = False
        connect(elsewhere, TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == [False]


class TestTheEndOfAnEmptyTable:
    def test_ends_nothing_while_the_roster_cannot_be_read_and_tries_again(self, holding, leases, time, ends):
        holding.watch_empty_table(TABLE)
        leases.reading_fails = [UNREACHABLE]

        with capture_logs() as logs:
            run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert logged_failures(logs) == [("empty_table_end.failed", "PresenceUnknownError")]
        assert ends.calls == [(TABLE, frozenset())]

    def test_ends_nothing_while_the_roster_is_unsettled_and_lists_nobody_at_the_table(
        self, holding, leases, time, ends
    ):
        holding.watch_empty_table(TABLE)
        leases.settled = False

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == []

    def test_reads_who_is_listed_while_the_roster_is_unsettled(self, holding, elsewhere, leases, time, ends):
        holding.watch_empty_table(TABLE)
        connect(elsewhere, TABLE, "anna", lambda: None)
        leases.settled = False

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == [(TABLE, {"anna"})]


class TestTheNextDeal:
    def test_tries_again_after_the_retry_delay_when_the_roster_cannot_be_read_and_then_deals(
        self, holding, leases, time, deals
    ):
        connect(holding, TABLE, "anna", lambda: None)
        leases.reading_fails = [UNREACHABLE]

        with capture_logs() as logs:
            run(holding.deal_now(TABLE))
        assert deals.calls == []
        assert logged_failures(logs) == [("next_deal.failed", "PresenceUnknownError")]

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert deals.calls == [(TABLE, {"anna"})]

    def test_acts_on_the_holders_an_unsettled_roster_lists_even_when_it_lists_nobody(self, holding, leases, deals):
        leases.settled = False

        run(holding.deal_now(TABLE))

        assert deals.calls == [(TABLE, frozenset())]

    def test_does_not_try_again_once_the_presence_has_stopped(self, holding, leases, time, deals):
        leases.reading_fails = [UNREACHABLE]
        run(holding.deal_now(TABLE))
        holding.stop()

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert deals.calls == []


class TestAStalledRoster:
    def test_counts_as_unknown_after_its_timeout_and_frees_nothing(self, holding, leases, time, releases, monkeypatch):
        monkeypatch.setattr(presence_module, "ROSTER_READ_TIMEOUT_SECONDS", 0.05)
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        leases.reading_hangs = True

        with capture_logs() as logs:
            run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == []
        assert logged_failures(logs) == [("chair_release.failed", "PresenceUnknownError")]

    def test_a_stop_ends_a_read_in_flight_and_the_guard_yields_nobody_at_once(
        self, holding, leases, deals, monkeypatch
    ):
        monkeypatch.setattr(presence_module, "ROSTER_READ_TIMEOUT_SECONDS", 30)
        leases.reading_hangs = True

        async def scenario():
            dealing = asyncio.create_task(holding.deal_now(TABLE))
            await leases.read_started.wait()
            holding.stop()
            await asyncio.wait_for(dealing, 5)

        run(scenario())

        assert deals.calls == [(TABLE, None)]

    def test_a_stop_ends_a_read_in_flight_and_the_freeing_is_not_due(
        self, holding, leases, time, releases, monkeypatch
    ):
        monkeypatch.setattr(presence_module, "ROSTER_READ_TIMEOUT_SECONDS", 30)
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        leases.reading_hangs = True
        leases.read_started.clear()

        async def scenario():
            advancing = asyncio.create_task(time.advance(HOLD_SECONDS))
            await leases.read_started.wait()
            holding.stop()
            await asyncio.wait_for(advancing, 5)

        run(scenario())

        assert releases.outcomes == [False]

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
    def test_ends_its_lease_and_starts_the_hold_though_the_closing_task_is_cancelled_meanwhile(self, holding, leases):
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

        assert leases.holders == []
        assert holding.hold_seconds_left([TABLE]) == {TABLE: {"anna": HOLD_SECONDS}}

    def test_starts_no_hold_while_the_roster_cannot_be_read_and_starts_it_on_the_retry(self, holding, leases, time):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        leases.reading_fails = [UNREACHABLE]

        with capture_logs() as logs:
            run(holding.close(subscription))
        assert holding.hold_seconds_left([TABLE]) == {}
        assert logged_failures(logs) == [("stream_close.failed", "ConnectionError")]

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert holding.hold_seconds_left([TABLE]) == {TABLE: {"anna": HOLD_SECONDS}}

    def test_starts_no_hold_while_the_roster_is_unsettled_and_does_not_list_the_account(self, holding, leases, time):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        leases.settled = False

        run(holding.close(subscription))
        assert holding.hold_seconds_left([TABLE]) == {}

        leases.settled = True
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert holding.hold_seconds_left([TABLE]) == {TABLE: {"anna": HOLD_SECONDS}}

    def test_starts_no_hold_when_the_account_streams_on_another_pod_once_the_roster_can_be_read(
        self, holding, elsewhere, leases, time
    ):
        connect(elsewhere, TABLE, "anna", lambda: None)
        subscription = connect(holding, TABLE, "anna", lambda: None)
        leases.reading_fails = [UNREACHABLE]

        run(holding.close(subscription))
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert holding.hold_seconds_left([TABLE]) == {}

    def test_starts_the_hold_once_a_lease_that_could_not_be_ended_has_left_the_roster(self, holding, leases, time):
        subscription = connect(holding, TABLE, "anna", lambda: None)
        leases.ending_fails = [UNREACHABLE]

        run(holding.close(subscription))
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert holding.hold_seconds_left([TABLE]) == {}

        leases.holders.clear()
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert holding.hold_seconds_left([TABLE]) == {TABLE: {"anna": HOLD_SECONDS}}

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

        with pytest.raises(ConnectionError):
            connect(holding, TABLE, "anna", wakes.callback("anna"))

        holding.wake_table(TABLE)
        assert wakes.counts == {"anna": 0}
