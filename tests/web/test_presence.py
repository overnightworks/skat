import asyncio
import threading

import pytest
from structlog.testing import capture_logs

from skat.web.presence import CHAIR_RELEASE_RETRY_SECONDS, ChairHold, LoopScheduler, Presence
from tests.support.idle_presence import idle_presence

TABLE = "t" * 32
OTHER_TABLE = "o" * 32


class Wakes:
    """What each subscriber was told: one counter per name."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def callback(self, name):
        self.counts.setdefault(name, 0)

        def wake():
            self.counts[name] += 1

        return wake


@pytest.fixture
def wakes():
    return Wakes()


@pytest.fixture
def presence():
    return idle_presence()


class TestConnectedAccounts:
    def test_nobody_is_connected_to_a_table_nobody_opened(self, presence):
        assert presence.connected(TABLE) == frozenset()

    def test_an_account_in_two_tabs_is_connected_once_until_its_last_tab_closes(self, presence, wakes):
        first = presence.subscribe(TABLE, "anna", wakes.callback("first"))
        second = presence.subscribe(TABLE, "anna", wakes.callback("second"))

        presence.unsubscribe(first)
        assert presence.connected(TABLE) == {"anna"}
        presence.unsubscribe(second)
        assert presence.connected(TABLE) == frozenset()

    def test_each_table_keeps_its_own_connections(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))

        assert presence.connected(OTHER_TABLE) == frozenset()

    def test_unsubscribing_twice_changes_nothing(self, presence, wakes):
        subscription = presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        presence.unsubscribe(subscription)
        presence.unsubscribe(subscription)

        assert presence.connected(TABLE) == {"ben"}


class TestPublishing:
    def test_a_member_connecting_wakes_every_other_stream_of_the_table_but_not_its_own(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 1, "ben": 0}

    def test_a_member_leaving_wakes_the_others(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        leaving = presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        presence.unsubscribe(leaving)

        assert wakes.counts == {"anna": 2, "ben": 0}

    def test_a_second_tab_of_a_connected_account_changes_nobodys_view_and_wakes_nobody(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        first = presence.subscribe(TABLE, "ben", wakes.callback("ben"))
        before = dict(wakes.counts)

        second = presence.subscribe(TABLE, "ben", wakes.callback("ben-again"))
        presence.unsubscribe(second)

        assert wakes.counts == {**before, "ben-again": 0}
        presence.unsubscribe(first)
        assert wakes.counts["anna"] == before["anna"] + 1

    def test_another_tables_streams_hear_nothing(self, presence, wakes):
        presence.subscribe(OTHER_TABLE, "anna", wakes.callback("anna"))

        presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 0, "ben": 0}


class TestWakingATable:
    def test_wakes_every_stream_of_that_table_and_no_other(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        presence.subscribe(TABLE, "ben", wakes.callback("ben"))
        presence.subscribe(OTHER_TABLE, "cem", wakes.callback("cem"))
        before = dict(wakes.counts)

        presence.wake_table(TABLE)

        assert wakes.counts == {"anna": before["anna"] + 1, "ben": before["ben"] + 1, "cem": before["cem"]}

    def test_waking_a_table_nobody_watches_is_harmless(self, presence):
        presence.wake_table(TABLE)


HOLD_SECONDS = 300
SERVER_START_SECONDS = 1000.0


class FakeTime:
    """A monotonic clock and a scheduler on it: `advance` runs every action that falls due, in due order."""

    def __init__(self, now=SERVER_START_SECONDS):
        self.now = now
        self._scheduled = []

    def clock(self):
        return self.now

    def schedule(self, delay, action):
        self._scheduled.append((self.now + delay, action))

    def cancel_all(self):
        self._scheduled.clear()

    @property
    def pending(self):
        return len(self._scheduled)

    async def advance(self, seconds):
        horizon = self.now + seconds
        while due := [entry for entry in self._scheduled if entry[0] <= horizon]:
            entry = min(due, key=lambda scheduled: scheduled[0])
            self._scheduled.remove(entry)
            self.now = max(self.now, entry[0])
            await entry[1]()
        self.now = horizon


class Releases:
    """The freeing command as the presence calls it: what it was asked, and what it answers or raises next."""

    def __init__(self):
        self.calls = []
        self.failures = []
        self.freed = True
        self.meanwhile = None
        self.within = None
        self.outcomes = []

    async def free_chair(self, table_id, account_id, due):
        self.calls.append((table_id, account_id))
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            self.meanwhile()
        with due as still_due:
            outcome = self.freed and still_due
            if self.within is not None:
                self.within()
        self.outcomes.append(outcome)
        return outcome


@pytest.fixture
def time():
    return FakeTime()


@pytest.fixture
def releases():
    return Releases()


@pytest.fixture
def holding(time, releases):
    return Presence(ChairHold(HOLD_SECONDS, time.clock, time, releases.free_chair))


def run(scenario):
    return asyncio.run(scenario)


class TestChairHold:
    def test_a_member_whose_last_stream_ended_keeps_the_chair_until_the_hold_has_passed(
        self, holding, time, releases, wakes
    ):
        holding.subscribe(TABLE, "ben", wakes.callback("ben"))
        leaving = holding.subscribe(TABLE, "anna", wakes.callback("anna"))
        holding.unsubscribe(leaving)

        run(time.advance(HOLD_SECONDS - 1))

        assert releases.calls == []

    def test_the_chair_is_freed_once_the_hold_has_passed_and_every_stream_is_woken(
        self, holding, time, releases, wakes
    ):
        holding.subscribe(TABLE, "ben", wakes.callback("ben"))
        holding.unsubscribe(holding.subscribe(TABLE, "anna", wakes.callback("anna")))
        woken_before = wakes.counts["ben"]

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == [(TABLE, "anna")]
        assert wakes.counts["ben"] == woken_before + 1

    def test_the_hold_counts_from_the_moment_the_last_stream_ended(self, holding, time, releases):
        leaving = holding.subscribe(TABLE, "anna", lambda: None)
        run(time.advance(40))
        holding.unsubscribe(leaving)

        run(time.advance(HOLD_SECONDS - 1))
        assert releases.calls == []
        run(time.advance(1))
        assert releases.calls == [(TABLE, "anna")]

    def test_a_member_who_returns_within_the_hold_keeps_the_chair_and_nothing_is_written(self, holding, time, releases):
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        run(time.advance(200))
        holding.subscribe(TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == []

    def test_only_the_timer_of_the_latest_leave_frees_the_chair(self, holding, time, releases):
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        run(time.advance(100))
        returned = holding.subscribe(TABLE, "anna", lambda: None)
        run(time.advance(50))
        holding.unsubscribe(returned)

        run(time.advance(HOLD_SECONDS - 150))
        assert releases.calls == []
        run(time.advance(150))
        assert releases.calls == [(TABLE, "anna")]

    def test_closing_one_of_two_tabs_schedules_no_timer(self, holding, time):
        first = holding.subscribe(TABLE, "anna", lambda: None)
        holding.subscribe(TABLE, "anna", lambda: None)

        holding.unsubscribe(first)

        assert time.pending == 0

    def test_a_member_standing_up_before_the_hold_ends_is_not_freed_again_and_nobody_is_woken(
        self, holding, time, releases, wakes
    ):
        holding.subscribe(TABLE, "ben", wakes.callback("ben"))
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.freed = False
        woken_before = wakes.counts["ben"]

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == [(TABLE, "anna")]
        assert wakes.counts["ben"] == woken_before

    def test_a_check_that_found_nothing_to_free_is_not_repeated(self, holding, time, releases):
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.freed = False

        run(time.advance(HOLD_SECONDS * 3))

        assert len(releases.calls) == 1

    def test_every_seated_member_counts_as_having_left_when_the_server_starts(self, holding, time, releases):
        holding.hold_chairs([(TABLE, "anna"), (OTHER_TABLE, "ben")])

        run(time.advance(HOLD_SECONDS - 1))
        assert releases.calls == []
        run(time.advance(1))
        assert set(releases.calls) == {(TABLE, "anna"), (OTHER_TABLE, "ben")}

    def test_a_member_connecting_after_the_start_keeps_the_chair(self, holding, time, releases):
        holding.hold_chairs([(TABLE, "anna")])
        holding.subscribe(TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == []

    def test_a_failed_freeing_wakes_nobody_logs_by_name_and_is_tried_again_until_it_commits(
        self, holding, time, releases, wakes
    ):
        holding.subscribe(TABLE, "ben", wakes.callback("ben"))
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.failures = [ConnectionError("account anna"), ConnectionError("account anna")]
        woken_before = wakes.counts["ben"]

        with capture_logs() as logs:
            run(time.advance(HOLD_SECONDS))
            assert wakes.counts["ben"] == woken_before
            run(time.advance(CHAIR_RELEASE_RETRY_SECONDS - 1))
            assert len(releases.calls) == 1
            run(time.advance(1))
            assert len(releases.calls) == 2
            run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert len(releases.calls) == 3
        assert wakes.counts["ben"] == woken_before + 1
        assert [(log["log_level"], log["error"]) for log in logs] == [("error", "ConnectionError")] * 2
        assert "anna" not in str(logs)

    def test_a_member_returning_while_the_freeing_waits_keeps_the_chair(self, holding, time, releases):
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.meanwhile = lambda: holding.subscribe(TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == [False]

    def test_a_leave_during_the_freeing_keeps_its_own_timer(self, holding, time, releases):
        returned = []

        def leaves_again():
            returned.append(holding.subscribe(TABLE, "anna", lambda: None))
            holding.unsubscribe(returned[0])

        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.meanwhile = leaves_again
        run(time.advance(HOLD_SECONDS))
        releases.meanwhile = None
        run(time.advance(HOLD_SECONDS))

        assert releases.calls == [(TABLE, "anna"), (TABLE, "anna")]

    @pytest.mark.parametrize("invalidation", ["reconnect", "stop"])
    def test_a_reconnect_or_a_stop_during_the_write_waits_until_it_is_committed(
        self, holding, time, releases, invalidation
    ):
        order = []
        invalidate = {
            "reconnect": lambda: holding.subscribe(TABLE, "anna", lambda: None),
            "stop": holding.stop,
        }[invalidation]
        invalidating = threading.Thread(target=lambda: (invalidate(), order.append("invalidated")))

        def invalidates_from_the_loop_while_the_write_runs():
            invalidating.start()
            invalidating.join(timeout=0.05)
            order.append("committed")

        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.within = invalidates_from_the_loop_while_the_write_runs

        run(time.advance(HOLD_SECONDS))
        invalidating.join()

        assert (releases.outcomes, order) == ([True], ["committed", "invalidated"])

    def test_a_freeing_that_waits_while_the_server_stops_frees_nothing(self, holding, time, releases):
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        releases.meanwhile = holding.stop

        run(time.advance(HOLD_SECONDS))

        assert (releases.outcomes, time.pending) == ([False], 0)

    def test_stopping_cancels_every_pending_check_and_a_stream_ending_afterwards_schedules_none(
        self, holding, time, releases
    ):
        holding.unsubscribe(holding.subscribe(TABLE, "anna", lambda: None))
        ending = holding.subscribe(OTHER_TABLE, "ben", lambda: None)

        holding.stop()
        holding.unsubscribe(ending)
        run(time.advance(HOLD_SECONDS * 2))

        assert (time.pending, releases.calls) == (0, [])


class TestLoopScheduler:
    def test_runs_the_action_after_its_delay(self):
        async def scenario():
            ran = asyncio.Event()

            async def action():
                ran.set()

            LoopScheduler().schedule(0, action)
            await asyncio.wait_for(ran.wait(), 2)

        run(scenario())

    def test_cancelling_all_stops_every_pending_action_from_running(self):
        async def scenario():
            ran = []

            async def action():
                ran.append(True)

            scheduler = LoopScheduler()
            scheduler.schedule(3600, action)
            scheduler.cancel_all()
            await asyncio.sleep(0)
            return ran, len(asyncio.all_tasks())

        ran, open_tasks = run(scenario())

        assert (ran, open_tasks) == ([], 1)
