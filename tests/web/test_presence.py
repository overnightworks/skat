import asyncio
import json
import threading
from contextlib import contextmanager
from functools import partial

import pytest
from structlog.testing import capture_logs

from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    NEXT_DEAL_PAUSE_SECONDS,
    ChairHold,
    LoopScheduler,
    NextDeal,
    Presence,
)
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.idle_presence import idle_presence
from tests.support.payload_cards import seated_three
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    HOLD_SECONDS,
    NAMED_FAILURE,
    OTHER_TABLE,
    TABLE,
    THIRD_PASS_COMMAND,
    Deals,
    OvertakenStore,
    connect,
    occupied_seats,
    pass_hand_in,
    post_pass,
    run,
)
from tests.web.support.skat import FakeTime, Skat


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
