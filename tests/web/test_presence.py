import asyncio
import threading

import pytest
from logline import current_traceparent, unit_trace

from skat.web.presence import (
    HOLD_SWEEP_EVERY_SECONDS,
    PAUSE_SWEEP_EVERY_SECONDS,
    ChairHold,
    EmptyTable,
    LoopScheduler,
    NextDeal,
    Presence,
)
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.idle_presence import (
    clear_no_hold,
    idle_agent_lease,
    idle_end_answers,
    idle_presence,
    idle_wakes,
    note_nothing,
    pause_no_table,
    store_no_leave,
)
from tests.support.in_memory_leases import InMemoryLeases
from tests.support.payload_cards import seated_three
from tests.web.support.presence import (
    OTHER_TABLE,
    TABLE,
    connect,
    end_the_first_game,
    occupied_seats,
    pass_hand_in,
    run,
)
from tests.web.support.skat import FakeTime, advance, read_the_first_round


@pytest.fixture
def presence():
    return idle_presence()


class TestConnectedAccounts:
    def test_nobody_is_connected_to_a_table_nobody_opened(self, presence):
        assert run(presence.connected(TABLE)) == frozenset()

    def test_an_account_in_two_tabs_is_connected_once_until_its_last_tab_closes(self, presence, wakes):
        first = connect(presence, TABLE, "anna", wakes.callback("first"))
        second = connect(presence, TABLE, "anna", wakes.callback("second"))

        run(presence.close(first))
        assert run(presence.connected(TABLE)) == {"anna"}
        run(presence.close(second))
        assert run(presence.connected(TABLE)) == frozenset()

    def test_each_table_keeps_its_own_connections(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))

        assert run(presence.connected(OTHER_TABLE)) == frozenset()

    def test_the_lobby_reads_every_table_from_one_read_of_the_roster(self, leases):
        presence = idle_presence(leases=leases)
        connect(presence, TABLE, "anna", lambda: None)
        connect(presence, OTHER_TABLE, "ben", lambda: None)
        before = leases.live_read_count

        connected = run(presence.connected_at([TABLE, OTHER_TABLE, "no-table"]))

        assert connected == {TABLE: {"anna"}, OTHER_TABLE: {"ben"}, "no-table": frozenset()}
        assert leases.live_read_count == before + 1

    def test_unsubscribing_twice_changes_nothing(self, presence, wakes):
        subscription = connect(presence, TABLE, "anna", wakes.callback("anna"))
        connect(presence, TABLE, "ben", wakes.callback("ben"))

        run(presence.close(subscription))
        run(presence.close(subscription))

        assert run(presence.connected(TABLE)) == {"ben"}


class TestPublishing:
    def test_a_member_connecting_wakes_every_other_stream_of_the_table_but_not_its_own(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        connect(presence, TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 1, "ben": 0}

    def test_a_member_leaving_wakes_the_others(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        leaving = connect(presence, TABLE, "ben", wakes.callback("ben"))

        run(presence.close(leaving))

        assert wakes.counts == {"anna": 2, "ben": 0}

    def test_a_second_tab_of_a_connected_account_changes_nobodys_view_and_wakes_nobody(self, presence, wakes):
        connect(presence, TABLE, "anna", wakes.callback("anna"))
        first = connect(presence, TABLE, "ben", wakes.callback("ben"))
        before = dict(wakes.counts)

        second = connect(presence, TABLE, "ben", wakes.callback("ben-again"))
        run(presence.close(second))

        assert wakes.counts == {**before, "ben-again": 0}
        run(presence.close(first))
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


class TestFinishingWrites:
    @pytest.mark.parametrize(
        ("swept", "seconds", "entered_with"),
        [
            pytest.param("hold", HOLD_SWEEP_EVERY_SECONDS, True, id="freeing"),
            pytest.param("pause", PAUSE_SWEEP_EVERY_SECONDS, frozenset({"anna"}), id="next-deal"),
            pytest.param("wait", HOLD_SWEEP_EVERY_SECONDS, frozenset(), id="empty-table"),
        ],
    )
    def test_finishing_writes_waits_for_a_worker_that_outlives_its_cancelled_sweep(self, swept, seconds, entered_with):
        started = threading.Event()
        release = threading.Event()
        committed = []

        def worker(due):
            with due as still_due:
                started.set()
                release.wait(5)
                committed.append(still_due)
            return still_due

        async def free_on_worker(table_id, account_id, absent):
            return await asyncio.to_thread(worker, absent)

        async def on_worker(table_id, connected_accounts):
            return await asyncio.to_thread(worker, connected_accounts)

        def due_when_swept(kind, due):
            async def due_now():
                return due if swept == kind else []

            return due_now

        async def scenario():
            time = FakeTime()
            presence = Presence(
                ChairHold(
                    time.clock,
                    time,
                    store_no_leave,
                    store_no_leave,
                    clear_no_hold,
                    due_when_swept("hold", [(TABLE, "anna")]),
                    free_on_worker,
                ),
                NextDeal(on_worker, on_worker, pause_no_table, pause_no_table, due_when_swept("pause", [TABLE])),
                EmptyTable(on_worker, note_nothing, due_when_swept("wait", [TABLE])),
                idle_agent_lease(),
                idle_wakes(),
                InMemoryLeases(),
                idle_end_answers(),
            )
            if swept == "pause":
                await presence.subscribe(TABLE, "anna", lambda: None)
            presence.start_sweeps()
            expiry = asyncio.create_task(time.advance(seconds))
            await asyncio.to_thread(started.wait, 5)
            expiry.cancel()
            finishing = asyncio.create_task(presence.finish_writes())
            await asyncio.sleep(0)
            waited = not finishing.done()
            release.set()
            await asyncio.wait_for(finishing, 5)
            return waited, list(committed)

        assert run(scenario()) == (True, [entered_with])


def leaves_the_table(server, table_id, headers):
    """The member opens the table's stream, reads its first round and closes it, which starts their hold."""
    with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=headers) as stream:
        read_the_first_round(stream.iter_lines())
        stream.close()
    server.client.cookies.clear()


def two_seated_at_a_new_table(server):
    """Anna opens a table and Ben sits in seat 2, so no hand is dealt; Cleo has no chair yet."""
    people = [server.member() for _ in range(3)]
    table_id = server.create(people[0][0]).json()["id"]
    server.sit(people[1][0], table_id, 2, command_id="command-sit-2")
    return table_id, people


class TestHoldAtADealtTable:
    def test_a_member_who_left_during_a_hand_keeps_the_chair_while_it_runs_and_after_it_ended(self, server, hold, time):
        table_id, people = seated_three(server)
        leaves_the_table(server, table_id, people[0][0])

        advance(server, time, hold.settings.chair_hold_seconds + 1)
        pass_hand_in(server, table_id, people)
        advance(server, time, hold.settings.chair_hold_seconds * 3)

        assert occupied_seats(server, table_id) == {1, 2, 3}

    def test_a_member_who_left_between_games_keeps_the_chair_and_the_hold_writes_nothing(self, server, hold, time):
        table_id, people = seated_three(server)
        end_the_first_game(server.store, table_id)
        leaves_the_table(server, table_id, people[1][0])
        before = server.store.tables[table_id]

        advance(server, time, hold.settings.chair_hold_seconds * 3)

        assert server.store.tables[table_id] == before

    def test_a_member_who_left_a_table_with_no_hand_dealt_loses_the_chair_after_the_hold(self, server, hold, time):
        table_id, people = two_seated_at_a_new_table(server)
        leaves_the_table(server, table_id, people[1][0])

        advance(server, time, hold.settings.chair_hold_seconds - 1)
        assert occupied_seats(server, table_id) == {1, 2}
        advance(server, time, 2)
        assert occupied_seats(server, table_id) == {1}

    def test_a_member_who_left_before_the_third_sit_keeps_the_chair_once_the_hold_ends(self, server, hold, time):
        table_id, people = two_seated_at_a_new_table(server)
        leaves_the_table(server, table_id, people[1][0])
        advance(server, time, hold.settings.chair_hold_seconds - 1)
        server.sit(people[2][0], table_id, 3, command_id="command-sit-3")

        advance(server, time, 2)

        assert occupied_seats(server, table_id) == {1, 2, 3}


class TestLoopScheduler:
    def test_runs_the_action_after_its_delay(self):
        async def scenario():
            ran = asyncio.Event()

            async def action():
                ran.set()

            LoopScheduler().schedule(0, action)
            await asyncio.wait_for(ran.wait(), 2)

        run(scenario())

    def test_runs_each_action_in_a_trace_of_its_own_and_not_in_the_one_that_scheduled_it(self):
        async def scenario():
            ran = asyncio.Event()
            traces = []

            async def action():
                traces.append(current_traceparent())
                ran.set()

            with unit_trace(None):
                scheduled_in = current_traceparent()
                LoopScheduler().schedule(0, action)
            await asyncio.wait_for(ran.wait(), 2)
            return scheduled_in, traces[0]

        scheduled_in, ran_in = run(scenario())

        assert ran_in is not None
        assert ran_in.split("-")[1] != scheduled_in.split("-")[1]

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
