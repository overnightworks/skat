import asyncio
import json
import threading
from contextlib import contextmanager
from functools import partial

import pytest
from structlog.testing import capture_logs

from skat.engine.deal import next_dealer
from skat.table.records import HandProgress
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    NEXT_DEAL_PAUSE_SECONDS,
    ChairHold,
    LoopScheduler,
    NextDeal,
    Presence,
)
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.idle_presence import idle_presence
from tests.support.payload_cards import DEALER_SEAT, cards_in, seated_three, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FakeTime, Skat, streams_of

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
        first = connect(presence, TABLE, "anna", wakes.callback("first"))
        second = connect(presence, TABLE, "anna", wakes.callback("second"))

        presence.unsubscribe(first)
        assert presence.connected(TABLE) == {"anna"}
        presence.unsubscribe(second)
        assert presence.connected(TABLE) == frozenset()

    def test_each_table_keeps_its_own_connections(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))

        assert presence.connected(OTHER_TABLE) == frozenset()

    def test_unsubscribing_twice_changes_nothing(self, presence, wakes):
        subscription = connect(presence, TABLE, "anna", wakes.callback("anna"))
        connect(presence, TABLE, "ben", wakes.callback("ben"))

        presence.unsubscribe(subscription)
        presence.unsubscribe(subscription)

        assert presence.connected(TABLE) == {"ben"}


class TestPublishing:
    def test_a_member_connecting_wakes_every_other_stream_of_the_table_but_not_its_own(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        connect(presence, TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 1, "ben": 0}

    def test_a_member_leaving_wakes_the_others(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        leaving = connect(presence, TABLE, "ben", wakes.callback("ben"))

        presence.unsubscribe(leaving)

        assert wakes.counts == {"anna": 2, "ben": 0}

    def test_a_second_tab_of_a_connected_account_changes_nobodys_view_and_wakes_nobody(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        first = connect(presence, TABLE, "ben", wakes.callback("ben"))
        before = dict(wakes.counts)

        second = connect(presence, TABLE, "ben", wakes.callback("ben-again"))
        presence.unsubscribe(second)

        assert wakes.counts == {**before, "ben-again": 0}
        presence.unsubscribe(first)
        assert wakes.counts["anna"] == before["anna"] + 1

    def test_another_tables_streams_hear_nothing(self, presence, wakes):
        connect(presence, OTHER_TABLE, "anna", wakes.callback("anna"))

        connect(presence, TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 0, "ben": 0}


class TestWakingATable:
    def test_wakes_every_stream_of_that_table_and_no_other(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        connect(presence, TABLE, "ben", wakes.callback("ben"))
        connect(presence, OTHER_TABLE, "cem", wakes.callback("cem"))
        before = dict(wakes.counts)

        presence.wake_table(TABLE)

        assert wakes.counts == {"anna": before["anna"] + 1, "ben": before["ben"] + 1, "cem": before["cem"]}

    def test_waking_a_table_nobody_watches_is_harmless(self, presence):
        presence.wake_table(TABLE)


HOLD_SECONDS = 300
FAILURE_NAMING_AN_ACCOUNT = "account anna"
NAMED_FAILURE = ("error", "ConnectionError")
THIRD_PASS_COMMAND = "pass-seat-3"


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
            await self.meanwhile()
        with due as still_due:
            outcome = self.freed and still_due
            if self.within is not None:
                await self.within()
        self.outcomes.append(outcome)
        return outcome


@pytest.fixture
def time():
    return FakeTime()


@pytest.fixture
def releases():
    return Releases()


class Deals:
    """The deal command as the presence calls it: what it was asked, and what it answers or raises next."""

    def __init__(self):
        self.calls = []
        self.failures = []
        self.dealt = True
        self.meanwhile = None

    async def deal_next(self, table_id, connected_accounts):
        self.calls.append((table_id, connected_accounts))
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            await self.meanwhile()
        return self.dealt


@pytest.fixture
def deals():
    return Deals()


@pytest.fixture
def holding(time, releases, deals):
    return Presence(
        ChairHold(HOLD_SECONDS, time.clock, time, releases.free_chair),
        NextDeal(NEXT_DEAL_PAUSE_SECONDS, deals.deal_next),
    )


def run(scenario):
    return asyncio.run(scenario)


def connect(presence, table_id, account_id, wake):
    return run(presence.subscribe(table_id, account_id, wake))


class TestChairHold:
    def test_a_member_whose_last_stream_ended_keeps_the_chair_until_the_hold_has_passed(
        self, holding, time, releases, wakes
    ):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        leaving = connect(holding, TABLE, "anna", wakes.callback("anna"))
        holding.unsubscribe(leaving)

        run(time.advance(HOLD_SECONDS - 1))

        assert releases.calls == []

    def test_the_chair_is_freed_once_the_hold_has_passed_and_every_stream_is_woken(
        self, holding, time, releases, wakes
    ):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        holding.unsubscribe(connect(holding, TABLE, "anna", wakes.callback("anna")))
        woken_before = wakes.counts["ben"]

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == [(TABLE, "anna")]
        assert wakes.counts["ben"] == woken_before + 1

    def test_the_hold_counts_from_the_moment_the_last_stream_ended(self, holding, time, releases):
        leaving = connect(holding, TABLE, "anna", lambda: None)
        run(time.advance(40))
        holding.unsubscribe(leaving)

        run(time.advance(HOLD_SECONDS - 1))
        assert releases.calls == []
        run(time.advance(1))
        assert releases.calls == [(TABLE, "anna")]

    def test_a_member_who_returns_within_the_hold_keeps_the_chair_and_nothing_is_written(self, holding, time, releases):
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        run(time.advance(200))
        connect(holding, TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == []

    def test_only_the_timer_of_the_latest_leave_frees_the_chair(self, holding, time, releases):
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        run(time.advance(100))
        returned = connect(holding, TABLE, "anna", lambda: None)
        run(time.advance(50))
        holding.unsubscribe(returned)

        run(time.advance(HOLD_SECONDS - 150))
        assert releases.calls == []
        run(time.advance(150))
        assert releases.calls == [(TABLE, "anna")]

    def test_closing_one_of_two_tabs_schedules_no_timer(self, holding, time):
        first = connect(holding, TABLE, "anna", lambda: None)
        connect(holding, TABLE, "anna", lambda: None)

        holding.unsubscribe(first)

        assert time.pending == 0

    def test_a_member_standing_up_before_the_hold_ends_is_not_freed_again_and_nobody_is_woken(
        self, holding, time, releases, wakes
    ):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        releases.freed = False
        woken_before = wakes.counts["ben"]

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == [(TABLE, "anna")]
        assert wakes.counts["ben"] == woken_before

    def test_a_check_that_found_nothing_to_free_is_not_repeated(self, holding, time, releases):
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
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
        connect(holding, TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.calls == []

    def test_a_failed_freeing_wakes_nobody_logs_by_name_and_is_tried_again_until_it_commits(
        self, holding, time, releases, wakes
    ):
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        releases.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT), ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
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
        assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE] * 2
        assert "anna" not in str(logs)

    def test_a_member_returning_while_the_freeing_waits_keeps_the_chair(self, holding, time, releases):
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))

        async def returns():
            await holding.subscribe(TABLE, "anna", lambda: None)

        releases.meanwhile = returns

        run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == [False]

    def test_a_leave_during_the_freeing_keeps_its_own_timer(self, holding, time, releases):
        returned = []

        async def leaves_again():
            returned.append(await holding.subscribe(TABLE, "anna", lambda: None))
            holding.unsubscribe(returned[0])

        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        releases.meanwhile = leaves_again
        run(time.advance(HOLD_SECONDS))
        releases.meanwhile = None
        run(time.advance(HOLD_SECONDS))

        assert releases.calls == [(TABLE, "anna"), (TABLE, "anna")]

    def test_a_reconnect_during_the_write_waits_for_its_commit_while_the_loop_stays_free(self, holding, time, releases):
        order = []
        writing = asyncio.Event()
        commit = asyncio.Event()

        async def write_until_released():
            writing.set()
            await commit.wait()
            order.append("committed")

        async def scenario():
            expiry = asyncio.create_task(time.advance(HOLD_SECONDS))
            await writing.wait()
            returning = asyncio.create_task(holding.subscribe(TABLE, "anna", lambda: None))
            await asyncio.wait_for(holding.subscribe(OTHER_TABLE, "ben", lambda: None), 2)
            await asyncio.sleep(0)
            waited = not returning.done()
            commit.set()
            await expiry
            await returning
            order.append("returned")
            return waited

        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        releases.within = write_until_released

        waited = run(scenario())

        assert (waited, releases.outcomes, order) == (True, [True], ["committed", "returned"])

    def test_a_cancelled_reconnect_during_a_failing_write_leaves_the_chair_to_the_retry(self, holding, time, releases):
        writing = asyncio.Event()
        fail = asyncio.Event()

        async def fail_after_reconnect():
            writing.set()
            await fail.wait()
            raise RuntimeError("store down")

        async def scenario():
            expiry = asyncio.create_task(time.advance(HOLD_SECONDS))
            await writing.wait()
            returning = asyncio.create_task(holding.subscribe(TABLE, "anna", lambda: None))
            await asyncio.sleep(0)
            returning.cancel()
            fail.set()
            await expiry
            releases.within = None
            await time.advance(CHAIR_RELEASE_RETRY_SECONDS)

        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        releases.within = fail_after_reconnect

        run(scenario())

        assert releases.outcomes == [True]

    def test_finishing_writes_waits_for_a_worker_that_outlives_its_cancelled_check(self):
        started = threading.Event()
        release = threading.Event()
        committed = []

        def worker(due):
            with due as still_due:
                started.set()
                release.wait(5)
                committed.append(still_due)
            return still_due

        async def free_on_worker(table_id, account_id, due):
            return await asyncio.to_thread(worker, due)

        async def scenario():
            time = FakeTime()
            presence = Presence(
                ChairHold(HOLD_SECONDS, time.clock, time, free_on_worker),
                NextDeal(NEXT_DEAL_PAUSE_SECONDS, Deals().deal_next),
            )
            presence.unsubscribe(await presence.subscribe(TABLE, "anna", lambda: None))
            expiry = asyncio.create_task(time.advance(HOLD_SECONDS))
            await asyncio.to_thread(started.wait, 5)
            expiry.cancel()
            finishing = asyncio.create_task(presence.finish_writes())
            await asyncio.sleep(0)
            waited = not finishing.done()
            release.set()
            await asyncio.wait_for(finishing, 5)
            return waited, list(committed)

        assert run(scenario()) == (True, [True])

    def test_a_freeing_that_waits_while_the_server_stops_frees_nothing(self, holding, time, releases):
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))

        async def stops():
            holding.stop()

        releases.meanwhile = stops

        run(time.advance(HOLD_SECONDS))

        assert (releases.outcomes, time.pending) == ([False], 0)

    def test_stopping_cancels_every_pending_check_and_a_stream_ending_afterwards_schedules_none(
        self, holding, time, releases
    ):
        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        ending = connect(holding, OTHER_TABLE, "ben", lambda: None)

        holding.stop()
        holding.unsubscribe(ending)
        run(time.advance(HOLD_SECONDS * 2))

        assert (time.pending, releases.calls) == (0, [])


@pytest.fixture
def hold(sign_in_settings):
    return sign_in_settings()


@pytest.fixture
def server(hold, time):
    """`create_app`'s own wiring and its own routes; only the clock and the timers run on the test's time."""
    skat = Skat(lambda: hold, chair_clock=time.clock, chair_scheduler=time)
    with skat.client:
        yield skat


def post_pass(skat, table_id, headers, *, command_id, version):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_SUFFIX}",
        json={"command_id": command_id, "version": version, "action": "pass"},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def pass_hand_in(skat, table_id, people):
    """`seated_three` dealt seat 1 the middlehand, seat 2 the rearhand and seat 3 the forehand."""
    for seat in (1, 2, 3):
        version = skat.store.tables[table_id].version
        answer = post_pass(skat, table_id, people[seat - 1][0], command_id=f"pass-seat-{seat}", version=version)
        assert answer.status_code == 200, answer.text


def occupied_seats(skat, table_id):
    return {chair.seat for chair in skat.store.tables[table_id].chairs if chair.occupant is not None}


class OvertakenStore(FakeTableStore):
    """A store another caller overtakes: `meanwhile` runs once when the next row lock is asked, `after_commit` once
    when the next transaction has committed."""

    def __init__(self):
        super().__init__()
        self.meanwhile = None
        self.after_commit = None

    @contextmanager
    def begin(self):
        with super().begin() as transaction:
            yield transaction
        if self.after_commit is not None:
            action, self.after_commit = self.after_commit, None
            action()

    def locked_table(self, table_id):
        if self.meanwhile is not None:
            action, self.meanwhile = self.meanwhile, None
            action()
        return super().locked_table(table_id)


@contextmanager
def one_second_before_the_hold_ends_after_two_passes(hold, time):
    """A server with three seated, away members and two passes made, one second before the hold would end."""
    store = OvertakenStore()
    server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)
    with server.client:
        table_id, people = seated_three(server)
        with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=people[0][0]) as s:
            next(s.iter_lines())
            s.close()
        server.client.cookies.clear()
        for seat in (1, 2):
            version = store.tables[table_id].version
            post_pass(server, table_id, people[seat - 1][0], command_id=f"pass-seat-{seat}", version=version)
        server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)
        yield server, store, table_id, people


def assert_fresh_hold_runs_a_full_hold(server, table_id, hold, time):
    assert occupied_seats(server, table_id) == {1, 2, 3}
    server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)
    assert occupied_seats(server, table_id) == {1, 2, 3}
    server.client.portal.call(time.advance, 2)
    assert occupied_seats(server, table_id) == set()


class TestHoldWhenTheHandEnds:
    def test_a_freeing_waiting_for_the_table_while_the_third_pass_ends_the_hand_leaves_the_fresh_hold_alone(
        self, hold, time
    ):
        with one_second_before_the_hold_ends_after_two_passes(hold, time) as (server, store, table_id, people):
            store.meanwhile = partial(
                post_pass,
                server,
                table_id,
                people[2][0],
                command_id=THIRD_PASS_COMMAND,
                version=store.tables[table_id].version,
            )

            server.client.portal.call(time.advance, 1)

            assert_fresh_hold_runs_a_full_hold(server, table_id, hold, time)

    def test_an_old_expiry_reaching_the_table_right_after_the_third_pass_committed_leaves_the_fresh_hold_alone(
        self, hold, time
    ):
        with one_second_before_the_hold_ends_after_two_passes(hold, time) as (server, store, table_id, people):
            store.after_commit = partial(server.client.portal.call, time.advance, 1)

            post_pass(
                server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=store.tables[table_id].version
            )

            assert_fresh_hold_runs_a_full_hold(server, table_id, hold, time)

    def test_a_member_away_when_the_hand_ends_keeps_the_chair_until_a_fresh_hold_has_passed(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()

        pass_hand_in(server, table_id, people)
        server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)

        assert occupied_seats(server, table_id) == {1, 2, 3}
        server.client.portal.call(time.advance, 2)
        assert occupied_seats(server, table_id) == set()

    def test_a_member_who_left_during_the_hand_keeps_the_chair_a_full_hold_after_it_ended(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=people[0][0]) as s:
            next(s.iter_lines())
            s.close()
        server.client.cookies.clear()
        server.client.portal.call(time.advance, hold.settings.chair_hold_seconds / 2)

        pass_hand_in(server, table_id, people)
        server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)

        assert occupied_seats(server, table_id) == {1, 2, 3}

    def test_a_stream_wakes_when_the_hold_after_the_hand_frees_a_chair(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()

        with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=people[3][0]) as s:
            messages = (line for line in s.iter_lines() if line.startswith("data: "))
            opened = json.loads(next(messages).removeprefix("data: "))
            server.client.cookies.clear()
            pass_hand_in(server, table_id, people)
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds + 1)
            freed = next(
                line
                for line in messages
                if all(chair["occupant_name"] is None for chair in json.loads(line.removeprefix("data: "))["chairs"])
            )

        assert json.loads(freed.removeprefix("data: "))["version"] > opened["version"]

    def test_a_member_connected_at_the_end_keeps_the_chair_and_starts_no_timer(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()

        with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=people[2][0]) as s:
            lines = s.iter_lines()
            next(lines)
            server.client.cookies.clear()
            pass_hand_in(server, table_id, people)
            two_holds_and_the_pause = 3
            assert time.pending == two_holds_and_the_pause
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds + 1)
            assert occupied_seats(server, table_id) == {3}

    def test_a_member_back_before_the_hold_ends_keeps_the_chair(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        pass_hand_in(server, table_id, people)
        server.client.portal.call(time.advance, hold.settings.chair_hold_seconds * 3 / 5)

        with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=people[1][0]) as s:
            lines = s.iter_lines()
            next(lines)
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds)
            assert occupied_seats(server, table_id) == {2}

    def test_the_same_third_pass_again_starts_no_timer(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        version = server.store.tables[table_id].version
        post_pass(server, table_id, people[0][0], command_id="pass-seat-1", version=version)
        post_pass(server, table_id, people[1][0], command_id="pass-seat-2", version=version + 1)
        first = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
        pending = time.pending

        again = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)

        assert (first.status_code, again.status_code) == (200, 200)
        assert time.pending == pending


class TestNextDealPause:
    def test_a_second_request_during_the_pause_starts_no_second_timer(self, holding, time, deals):
        holding.deal_soon(TABLE)
        holding.deal_soon(TABLE)

        assert time.pending == 1
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert len(deals.calls) == 1

    def test_each_table_has_its_own_pause(self, holding, time):
        holding.deal_soon(TABLE)
        holding.deal_soon(OTHER_TABLE)

        assert time.pending == 2

    def test_asks_for_the_deal_with_who_is_connected_when_the_pause_ends(self, holding, time, deals):
        holding.deal_soon(TABLE)
        connect(holding, TABLE, "anna", lambda: None)

        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert deals.calls == [(TABLE, frozenset({"anna"}))]

    def test_a_deal_wakes_the_table_and_a_refused_deal_wakes_nobody(self, holding, time, deals, wakes):
        connect(holding, TABLE, "anna", wakes.callback("anna"))
        before = wakes.counts["anna"]

        holding.deal_soon(TABLE)
        deals.dealt = False
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert wakes.counts["anna"] == before

        holding.deal_soon(TABLE)
        deals.dealt = True
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert wakes.counts["anna"] == before + 1

    def test_a_request_while_the_deal_runs_starts_a_fresh_pause_after_it(self, holding, time, deals):
        async def another_request():
            deals.meanwhile = None
            holding.deal_soon(TABLE)

        deals.meanwhile = another_request
        holding.deal_soon(TABLE)

        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert time.pending == 1

    def test_a_failed_deal_is_logged_by_name_wakes_nobody_and_leaves_the_next_request_free(
        self, holding, time, deals, wakes
    ):
        connect(holding, TABLE, "anna", wakes.callback("anna"))
        before = wakes.counts["anna"]
        deals.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]

        holding.deal_soon(TABLE)
        with capture_logs() as logs:
            run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert wakes.counts["anna"] == before
        assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
        assert "anna" not in str(logs)
        holding.deal_soon(TABLE)
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert wakes.counts["anna"] == before + 1

    def test_the_server_stopping_during_the_pause_cancels_the_deal_and_a_later_request_starts_none(
        self, holding, time, deals
    ):
        holding.deal_soon(TABLE)

        holding.stop()
        holding.deal_soon(OTHER_TABLE)
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS * 2))

        assert (time.pending, deals.calls) == (0, [])


def view_of_version(messages, version):
    return next(view for view in messages if view["version"] >= version)


def advance(server, time, seconds):
    server.client.portal.call(time.advance, seconds)


class TestNextHandComes:
    def test_the_next_dealer_deals_when_the_pause_ends_and_not_a_moment_before(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]) as streams:
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS - 0.001)
            assert server.store.tables[table_id] == passed_in

            advance(server, time, 0.001)
            record = server.store.tables[table_id]
            assert record.dealer == next_dealer(DEALER_SEAT)
            assert [len(cards) for cards in record.hand.hands.values()] == [10, 10, 10]
            assert record.progress == HandProgress()
            assert record.version == passed_in.version + 1
            for messages in streams:
                view = view_of_version(messages, record.version)
                assert view["passed_in"] is None
                position = next(chair["hand"]["position"] for chair in view["chairs"] if chair["is_mine"])
                assert cards_in(view) == wire_cards(getattr(record.hand, position))

    def test_a_stream_opening_during_the_pause_neither_cuts_it_short_nor_stretches_it(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]
            pending = time.pending
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 2)

            with streams_of(server, table_id, people[3:]):
                assert time.pending == pending
                advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 2 - 0.001)
                assert server.store.tables[table_id] == passed_in

                advance(server, time, 0.001)
                assert server.store.tables[table_id].version == passed_in.version + 1

                advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)
                assert server.store.tables[table_id].version == passed_in.version + 1

    def test_a_member_away_when_the_pause_ends_keeps_the_table_waiting_and_their_hold_running(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:2]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS)
            assert server.store.tables[table_id] == passed_in

            advance(server, time, hold.settings.chair_hold_seconds - NEXT_DEAL_PAUSE_SECONDS - 1)
            assert occupied_seats(server, table_id) == {1, 2, 3}
            assert server.store.tables[table_id] == passed_in

    def test_a_returning_member_gets_a_fresh_pause_and_then_the_deal_and_keeps_the_chair(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:2]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS + 10)

            with streams_of(server, table_id, people[2:3]):
                advance(server, time, NEXT_DEAL_PAUSE_SECONDS - 0.001)
                assert server.store.tables[table_id] == passed_in

                advance(server, time, 0.001)
                assert server.store.tables[table_id].version == passed_in.version + 1

                advance(server, time, hold.settings.chair_hold_seconds)
                assert occupied_seats(server, table_id) == {1, 2, 3}

    def test_the_hold_of_an_away_member_frees_the_chair_with_no_deal_and_the_filling_sit_deals_at_once(
        self, server, hold, time
    ):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:2]):
            pass_hand_in(server, table_id, people)
            advance(server, time, hold.settings.chair_hold_seconds + 1)
            assert occupied_seats(server, table_id) == {1, 2}
            assert server.store.tables[table_id].hand is None

            server.client.cookies.clear()
            answer = server.sit(people[3][0], table_id, 3, command_id="command-sit-away")

        assert answer.status_code == 200, answer.text
        record = server.store.tables[table_id]
        assert record.hand is not None
        assert record.dealer == next_dealer(DEALER_SEAT)

    def test_standing_up_during_the_pause_is_allowed_and_the_pause_then_deals_nothing(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)

            standing = server.stand(people[0][0], table_id)
            server.client.cookies.clear()
            assert standing.status_code == 200, standing.text
            after_standing = server.store.tables[table_id]

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

            assert server.store.tables[table_id] == after_standing
            assert after_standing.hand is None

    def test_a_retry_of_the_third_pass_during_the_pause_and_after_the_deal_starts_no_timer_and_no_deal(
        self, server, time
    ):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            version = server.store.tables[table_id].version
            post_pass(server, table_id, people[0][0], command_id="pass-seat-1", version=version)
            post_pass(server, table_id, people[1][0], command_id="pass-seat-2", version=version + 1)
            first = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
            pending = time.pending

            during = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
            assert (first.status_code, during.status_code, time.pending) == (200, 200, pending)

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS)
            dealt = server.store.tables[table_id]
            assert dealt.hand is not None

            after = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            assert after.status_code == 200
            assert server.store.tables[table_id] == dealt

    @pytest.mark.parametrize("seated", [True, False], ids=["a-hand-runs", "never-dealt"])
    def test_a_stream_opening_when_no_hand_was_passed_in_changes_nothing(self, server, time, seated):
        if seated:
            table_id, people = seated_three(server)
        else:
            people = [server.member()]
            table_id = server.create(people[0][0]).json()["id"]
        server.client.cookies.clear()
        before = server.store.tables[table_id]

        with streams_of(server, table_id, people[:1]):
            assert time.pending == 0
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            assert server.store.tables[table_id] == before

    def test_a_store_failure_in_the_deal_is_named_changes_nothing_and_the_next_stream_opening_deals(self, hold, time):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)

        def store_goes_down():
            raise ConnectionError(FAILURE_NAMING_AN_ACCOUNT)

        with server.client:
            table_id, people = seated_three(server)
            server.client.cookies.clear()
            with streams_of(server, table_id, people[:3]):
                pass_hand_in(server, table_id, people)
                passed_in = store.tables[table_id]
                store.meanwhile = store_goes_down

                with capture_logs() as logs:
                    advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

                assert store.tables[table_id] == passed_in
                assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
                assert "anna" not in str(logs)

                with streams_of(server, table_id, people[3:]):
                    advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

                    assert store.tables[table_id].version == passed_in.version + 1

    def test_the_server_stopping_during_the_pause_deals_nothing(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]

            server.client.portal.call(server.app.state.stop_streams)
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            assert (time.pending, server.store.tables[table_id]) == (0, passed_in)


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
