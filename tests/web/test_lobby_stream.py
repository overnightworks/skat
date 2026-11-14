"""The lobby stream sends an account the tables it holds a chair at, and no other, as the named event `mine`."""

import asyncio
import json
from contextlib import nullcontext

import pytest

from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CloseTable, CreateTable, SitDown, TableId
from skat.table.service import TableService
from skat.web.lobby import LOBBY_EVENTS_PATH
from skat.web.streams import IDLE_HEARTBEAT, StreamEvent, stream_messages
from skat.web.wakes import AccountTopic
from tests.support.fake_tables import FakeTableStore
from tests.web.support.agent import SUBJECT
from tests.web.support.lobby_scene import ANNA, BEN, CLEO, Scene, ids_of, next_mine, next_open
from tests.web.support.skat import FETCH, Skat
from tests.web.support.streams import (
    SHORT_HEARTBEAT_SECONDS,
    Admission,
    admitting,
    next_item,
    run_on_a_loop_of_its_own,
)


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture(
    params=[
        pytest.param("in memory", id="in-memory"),
        pytest.param("stored", id="stored", marks=pytest.mark.postgres),
    ]
)
def tables_skat(request, hold, issuer):
    """The app over each store the tables can live in, with a heartbeat short enough to read between events."""
    options = {"issuer_transports": issuer.transports, "heartbeat_seconds": SHORT_HEARTBEAT_SECONDS}
    if request.param == "in memory":
        with (skat := Skat(lambda: hold, **options)).client:
            yield skat
        return
    engine = create_store_engine(request.getfixturevalue("database_url"))
    with (skat := Skat(lambda: hold, store=PostgresTableTransactions(engine), **options)).client:
        yield skat
    engine.dispose()


class TestWhoReceivesWhichTable:
    def test_a_person_who_holds_no_chair_gets_one_mine_with_an_empty_list_and_then_heartbeats(self):
        scene = Scene()

        async def scenario():
            stream = scene.stream(ANNA, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            first = await next_mine(stream)
            after = [await next_item(stream) for _ in range(2)]
            await stream.aclose()
            return first, after

        assert run_on_a_loop_of_its_own(scenario()) == ([], [IDLE_HEARTBEAT, IDLE_HEARTBEAT])

    def test_a_table_the_person_never_sat_at_reaches_him_in_no_message_whatever_happens_at_it(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(BEN, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            messages = [await next_item(stream)]
            scene.sit(CLEO, table_id, 2)
            scene.presence.wake_table(table_id)
            messages += [await next_item(stream) for _ in range(2)]
            await stream.aclose()
            return messages

        messages = run_on_a_loop_of_its_own(scenario())

        assert [message.data for message in messages if message is not IDLE_HEARTBEAT] == ['{"tables":[]}']

    def test_a_table_a_person_sits_at_reaches_the_lobby_he_has_open_through_his_account(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(BEN)
            before = await next_mine(stream)
            scene.sit(BEN, table_id, 2)
            after = await next_mine(stream)
            await stream.aclose()
            return before, after

        before, after = run_on_a_loop_of_its_own(scenario())

        assert (before, ids_of(after)) == ([], [table_id])

    def test_a_table_a_person_opens_reaches_the_lobby_he_has_open(self):
        scene = Scene()

        async def scenario():
            stream = scene.stream(ANNA)
            before = await next_mine(stream)
            table_id = scene.open_table(ANNA)
            scene.wakes.wake(AccountTopic(ANNA.account_id))
            after = await next_mine(stream)
            await stream.aclose()
            return before, table_id, after

        before, table_id, after = run_on_a_loop_of_its_own(scenario())

        assert (before, ids_of(after)) == ([], [table_id])

    def test_another_member_who_sits_is_named_at_the_opener_and_a_stand_up_frees_the_chair_there(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            annas, bens = scene.stream(ANNA), scene.stream(BEN)
            await next_mine(annas)
            await next_mine(bens)
            scene.sit(BEN, table_id, 2)
            named, bens_entry = await next_mine(annas), await next_mine(bens)
            scene.stand(BEN, table_id)
            freed, bens_after = await next_mine(annas), await next_mine(bens)
            await annas.aclose()
            await bens.aclose()
            return named, bens_entry, freed, bens_after

        named, bens_entry, freed, bens_after = run_on_a_loop_of_its_own(scenario())

        assert [chair["occupant_name"] for chair in named[0]["chairs"]] == ["Anna", "Ben", None]
        assert [chair["is_mine"] for chair in bens_entry[0]["chairs"]] == [False, True, False]
        assert [chair["occupant_name"] for chair in freed[0]["chairs"]] == ["Anna", None, None]
        assert bens_after == []

    def test_a_change_at_a_held_table_reaches_the_lobby_through_the_tables_topic(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(ANNA)
            await next_mine(stream)
            scene.service.sit(BEN, SitDown("sit-ben", table_id, 2), frozenset())
            scene.presence.wake_table(table_id)
            after = await next_mine(stream)
            await stream.aclose()
            return after

        assert [chair["occupant_name"] for chair in run_on_a_loop_of_its_own(scenario())[0]["chairs"]] == [
            "Anna",
            "Ben",
            None,
        ]

    def test_a_stream_opened_after_a_drop_starts_with_the_whole_current_list(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            dropped = scene.stream(ANNA)
            await next_mine(dropped)
            await dropped.aclose()
            scene.sit(BEN, table_id, 2)
            reconnected = scene.stream(ANNA)
            first = await next_mine(reconnected)
            await reconnected.aclose()
            return first

        first = run_on_a_loop_of_its_own(scenario())

        assert [chair["occupant_name"] for chair in first[0]["chairs"]] == ["Anna", "Ben", None]

    def test_a_table_that_ends_leaves_the_next_mine(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(ANNA)
            before = await next_mine(stream)
            assert scene.service.end_empty_table(TableId(table_id), nullcontext(frozenset()), 0)
            scene.presence.wake_table(table_id)
            after = await next_mine(stream)
            await stream.aclose()
            return before, after

        before, after = run_on_a_loop_of_its_own(scenario())

        assert (ids_of(before), after) == ([table_id], [])


class TestTheWakes:
    def test_a_commit_at_another_table_does_not_wake_the_lobby_and_a_commit_at_a_held_one_does(self):
        scene = Scene()
        held, other = scene.open_table(ANNA), scene.open_table(BEN)
        woken = []

        async def scenario():
            source = scene.source(ANNA)
            await source.open(lambda: woken.append(1))
            await source.read(ANNA)
            scene.presence.wake_table(other)
            unrelated = len(woken)
            scene.presence.wake_table(held)
            source.close()
            return unrelated, len(woken)

        assert run_on_a_loop_of_its_own(scenario()) == (0, 1)

    def test_a_table_opened_before_the_first_read_of_the_open_list_wakes_it(self):
        scene = Scene()
        woken = []

        async def scenario():
            source = scene.open_source(BEN)
            await source.open(lambda: woken.append(1))
            scene.open_table(ANNA)
            source.close()
            return len(woken)

        assert run_on_a_loop_of_its_own(scenario()) == 1

    def test_a_table_that_ended_holds_no_registration_after_the_next_read(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        woken = []

        async def scenario():
            source = scene.source(ANNA)
            await source.open(lambda: woken.append(1))
            await source.read(ANNA)
            scene.service.end_empty_table(TableId(table_id), nullcontext(frozenset()), 0)
            await source.read(ANNA)
            scene.presence.wake_table(table_id)
            source.close()
            return len(woken)

        assert run_on_a_loop_of_its_own(scenario()) == 0

    def test_a_commit_at_one_table_wakes_only_its_holders_among_fifty_lobbies_and_none_is_left_after_they_close(self):
        scene = Scene()
        people = [Actor(f"account-{number}", f"Member {number}") for number in range(50)]
        tables = [scene.open_table(person) for person in people]
        woken = {person.account_id: 0 for person in people}

        def counting(person):
            def wake():
                woken[person.account_id] += 1

            return wake

        async def scenario():
            sources = []
            for person in people:
                source = scene.source(person)
                await source.open(counting(person))
                await source.read(person)
                sources.append(source)
            scene.presence.wake_table(tables[7])
            woken_by_the_commit = {account for account, count in woken.items() if count}
            for source in sources:
                source.close()
            scene.wakes.wake_all()
            return woken_by_the_commit, sum(woken.values())

        by_the_commit, total = run_on_a_loop_of_its_own(scenario())

        assert (by_the_commit, total) == ({people[7].account_id}, 1)

    def test_opening_the_lobby_is_no_presence_at_any_table(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(ANNA)
            await next_mine(stream)
            during = scene.presence.connected(table_id)
            await stream.aclose()
            return during, scene.presence.connected(table_id)

        assert run_on_a_loop_of_its_own(scenario()) == (frozenset(), frozenset())


class TestWhoIsAwayReachesAnOpenLobby:
    def test_another_members_leaving_and_returning_changes_his_chair_and_the_end_of_the_table_in_the_lobby_held_open(
        self,
    ):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)

        async def scenario():
            stream = scene.stream(ANNA)
            nobody = (await next_mine(stream))[0]
            subscription = await scene.presence.subscribe(table_id, BEN.account_id, lambda: None)
            returned = (await next_mine(stream))[0]
            scene.presence.unsubscribe(subscription)
            left = (await next_mine(stream))[0]
            await stream.aclose()
            return nobody, returned, left

        def view(entry):
            return [chair["is_away"] for chair in entry["chairs"]], entry["ends_at"] is None

        nobody, returned, left = run_on_a_loop_of_its_own(scenario())

        assert (view(nobody), view(returned), view(left)) == (
            ([False, True, True], False),
            ([False, False, True], True),
            ([False, True, True], False),
        )


class PlayingInTheWindow(TableService):
    """A service whose next index read runs `window` after it has read and before it answers: a commit that lands
    between the index read and the swap of the registration.
    """

    def __init__(self, store):
        super().__init__(store)
        self.window = None

    def held_tables(self, account_id):
        held = super().held_tables(account_id)
        window, self.window = self.window, None
        if window is not None:
            window()
        return held


class TestTheWindowBetweenTheIndexReadAndTheSwap:
    def commit_in_the_window(self, scene, loop, commit, topic):
        """Arms the service: the commit runs on the worker, its wake is delivered on the loop, as the routes do."""

        def window():
            commit()
            loop.call_soon_threadsafe(scene.wakes.wake, topic)

        scene.service.window = window

    def test_a_sit_in_the_window_of_the_first_read_arrives_without_waiting_for_a_heartbeat(self):
        scene = Scene(PlayingInTheWindow(FakeTableStore()))
        table_id = scene.open_table(ANNA)

        async def scenario():
            self.commit_in_the_window(
                scene,
                asyncio.get_running_loop(),
                lambda: scene.service.sit(BEN, SitDown("sit-ben", table_id, 2), frozenset()),
                AccountTopic(BEN.account_id),
            )
            stream = scene.stream(BEN)
            first = await next_mine(stream)
            second = await next_mine(stream)
            await stream.aclose()
            return first, second

        first, second = run_on_a_loop_of_its_own(scenario())

        assert (first, ids_of(second)) == ([], [table_id])

    def test_a_sit_and_a_change_at_a_held_table_in_the_window_of_a_later_read_arrive_without_a_heartbeat(self):
        scene = Scene(PlayingInTheWindow(FakeTableStore()))
        held, joined = scene.open_table(ANNA), scene.open_table(ANNA)
        scene.sit(BEN, held, 2)

        def commit():
            scene.service.sit(BEN, SitDown("sit-ben-joined", joined, 2), frozenset())
            scene.service.sit(CLEO, SitDown("sit-cleo-held", held, 3), frozenset())

        async def scenario():
            stream = scene.stream(BEN)
            before = await next_mine(stream)
            loop = asyncio.get_running_loop()
            self.commit_in_the_window(scene, loop, commit, AccountTopic(BEN.account_id))
            scene.presence.wake_table(held)
            reads = [await next_mine(stream), await next_mine(stream)]
            await stream.aclose()
            return before, reads

        before, reads = run_on_a_loop_of_its_own(scenario())

        assert ids_of(before) == [held]
        assert sorted(ids_of(reads[-1])) == sorted([held, joined])
        held_entry = next(entry for entry in reads[-1] if entry["id"] == held)
        assert [chair["occupant_name"] for chair in held_entry["chairs"]] == ["Anna", "Ben", "Cleo"]


class CountingFullReads(TableService):
    """A service that counts the full reads of the lobby's lists: the reads of every table's record."""

    def __init__(self, store):
        super().__init__(store)
        self.mine_reads = 0
        self.open_reads = 0

    def my_tables(self, *arguments):
        self.mine_reads += 1
        return super().my_tables(*arguments)

    def open_tables(self, *arguments):
        self.open_reads += 1
        return super().open_tables(*arguments)


class TestTheIdleHeartbeat:
    def test_a_heartbeat_with_nothing_moved_sends_only_the_comment_line_and_reads_no_table_again(self):
        scene = Scene(CountingFullReads(FakeTableStore()))
        scene.sit(BEN, scene.open_table(ANNA), 2)
        scene.open_table(CLEO)

        async def scenario():
            stream = stream_messages(
                [scene.source(BEN), scene.open_source(BEN)],
                admitting(BEN),
                lambda: scene.presence.stopped,
                heartbeat_seconds=SHORT_HEARTBEAT_SECONDS,
            )
            firsts = [await next_item(stream), await next_item(stream)]
            beats = [await next_item(stream) for _ in range(3)]
            await stream.aclose()
            return firsts, beats

        firsts, beats = run_on_a_loop_of_its_own(scenario())

        assert [item.event for item in firsts] == [StreamEvent.MINE, StreamEvent.OPEN]
        assert (beats, scene.service.mine_reads, scene.service.open_reads) == ([IDLE_HEARTBEAT] * 3, 1, 1)

    def test_a_commit_at_a_held_table_that_no_wake_announced_arrives_with_the_heartbeat(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)

        async def scenario():
            stream = scene.stream(BEN, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            before = await next_mine(stream)
            scene.service.sit(CLEO, SitDown("sit-cleo", table_id, 3), frozenset())
            after = await next_mine(stream)
            await stream.aclose()
            return before, after

        before, after = run_on_a_loop_of_its_own(scenario())

        assert [[chair["occupant_name"] for chair in tables[0]["chairs"]] for tables in (before, after)] == [
            ["Anna", "Ben", None],
            ["Anna", "Ben", "Cleo"],
        ]

    def test_a_table_a_stranger_opens_without_a_wake_arrives_in_the_open_list_with_the_heartbeat(self):
        scene = Scene()

        async def scenario():
            stream = scene.open_stream(BEN, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            before = await next_open(stream)
            opened = scene.service.create(CLEO, CreateTable(command_id="open-without-a-wake")).id
            after = await next_open(stream)
            await stream.aclose()
            return before, after, opened

        before, after, opened = run_on_a_loop_of_its_own(scenario())

        assert (before, ids_of(after)) == ([], [opened])


def mine_of_anna(scene):
    return scene.source(ANNA)


def open_list_of_cleo(scene):
    return scene.open_source(CLEO)


async def ben_sits(scene, table_id):
    scene.service.sit(BEN, SitDown("sit-ben", table_id, 2), frozenset())


async def ben_watches(scene, table_id):
    await scene.presence.subscribe(table_id, BEN.account_id, lambda: None)


async def ben_opens_a_table(scene, table_id):
    scene.service.create(BEN, CreateTable(command_id="open-ben"))


async def the_lease_of_a_sitter_starts(scene, table_id):
    scene.presence.renew_lease(ANNA.account_id)


async def the_lease_of_a_stranger_starts(scene, table_id):
    scene.presence.renew_lease(BEN.account_id)


async def anna_closes_the_table(scene, table_id):
    scene.service.close(ANNA, CloseTable("close-anna", table_id))


async def nothing_happens(scene, table_id):
    pass


class TestWhatMovesASource:
    @pytest.mark.parametrize(
        ("source_of", "happens", "moved"),
        [
            pytest.param(mine_of_anna, nothing_happens, False, id="mine-nothing"),
            pytest.param(mine_of_anna, ben_sits, True, id="mine-a-commit-at-a-held-table"),
            pytest.param(mine_of_anna, ben_watches, True, id="mine-a-watcher-at-a-held-table"),
            pytest.param(mine_of_anna, the_lease_of_a_sitter_starts, True, id="mine-the-lease-of-a-sitter"),
            pytest.param(
                mine_of_anna, the_lease_of_a_stranger_starts, False, id="mine-the-lease-of-an-unseated-account"
            ),
            pytest.param(mine_of_anna, anna_closes_the_table, True, id="mine-a-held-table-ends"),
            pytest.param(mine_of_anna, ben_opens_a_table, False, id="mine-a-table-of-a-stranger"),
            pytest.param(open_list_of_cleo, nothing_happens, False, id="open-nothing"),
            pytest.param(open_list_of_cleo, ben_sits, True, id="open-a-commit-at-a-listed-table"),
            pytest.param(open_list_of_cleo, ben_watches, True, id="open-a-watcher-at-a-listed-table"),
            pytest.param(open_list_of_cleo, ben_opens_a_table, True, id="open-a-table-opened"),
            pytest.param(open_list_of_cleo, the_lease_of_a_sitter_starts, True, id="open-the-lease-of-a-sitter"),
            pytest.param(
                open_list_of_cleo, the_lease_of_a_stranger_starts, False, id="open-the-lease-of-an-unseated-account"
            ),
            pytest.param(open_list_of_cleo, anna_closes_the_table, True, id="open-a-listed-table-ends"),
        ],
    )
    def test_a_source_has_moved_when_the_versions_of_its_tables_or_who_is_present_there_changed(
        self, source_of, happens, moved
    ):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            source = source_of(scene)
            await source.open(lambda: None)
            await source.read(ANNA)
            await happens(scene, table_id)
            answer = await source.moved(ANNA)
            source.close()
            return answer

        assert run_on_a_loop_of_its_own(scenario()) is moved


class TestTheStreamEnds:
    def test_a_wake_that_changes_nothing_sends_nothing_and_the_next_item_is_the_heartbeat_marker(self):
        scene = Scene()
        scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(ANNA, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            await next_mine(stream)
            scene.wakes.wake(AccountTopic(ANNA.account_id))
            item = await next_item(stream)
            await stream.aclose()
            return item

        assert run_on_a_loop_of_its_own(scenario()) is IDLE_HEARTBEAT

    def test_a_refused_session_ends_the_stream_at_the_next_change_with_nothing_more_sent(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(BEN, admit=Admission(True, False, actor=BEN))
            await next_mine(stream)
            scene.sit(BEN, table_id, 2)
            return [item async for item in stream]

        assert run_on_a_loop_of_its_own(scenario()) == []

    def test_stopping_the_presence_ends_every_lobby_and_a_lobby_opened_afterwards_ends_at_once(self):
        scene = Scene()

        async def scenario():
            open_lobby = scene.stream(ANNA)
            await next_mine(open_lobby)
            scene.presence.stop()
            ended = [item async for item in open_lobby]
            later = [item async for item in scene.stream(BEN)]
            return ended, later

        assert run_on_a_loop_of_its_own(scenario()) == ([], [])


class TestWhatTheEntriesCarry:
    def test_a_dealt_table_names_whose_turn_it_is_and_the_one_who_has_to_act_is_told_so(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)

        async def scenario():
            streams = {person.account_id: scene.stream(person) for person in (ANNA, BEN, CLEO)}
            entries = {account: (await next_mine(stream))[0] for account, stream in streams.items()}
            for stream in streams.values():
                await stream.aclose()
            return entries

        entries = run_on_a_loop_of_its_own(scenario())

        waiting = [account for account, entry in entries.items() if entry["waits_on"] == "turn"]
        assert len(waiting) == 1
        assert all(entry["dealt"] for entry in entries.values())
        assert [chair["is_turn"] for chair in entries[waiting[0]]["chairs"]].count(True) == 1

    def test_a_person_standing_up_during_a_hand_leaves_his_mine_and_the_hand_waits_for_nobody_else(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)
        everyone = (ANNA, BEN, CLEO)

        async def scenario():
            streams = {person.account_id: scene.stream(person) for person in everyone}
            first = {account: (await next_mine(stream))[0] for account, stream in streams.items()}
            on_turn = next(person for person in everyone if first[person.account_id]["waits_on"] == "turn")
            leaving = next(person for person in everyone if person is not on_turn)
            scene.stand(leaving, table_id)
            after_on_turn = (await next_mine(streams[on_turn.account_id]))[0]
            after_leaving = await next_mine(streams[leaving.account_id])
            for stream in streams.values():
                await stream.aclose()
            return after_on_turn, after_leaving

        after_on_turn, after_leaving = run_on_a_loop_of_its_own(scenario())

        assert (after_on_turn["waits_on"], after_on_turn["awaits_you"], after_leaving) == (None, False, [])


ENTRY_FIELDS = {
    "id",
    "private",
    "title_name",
    "game_number",
    "game_count",
    "dealt",
    "awaits_you",
    "waits_on",
    "result_waits",
    "series_over",
    "ends_at",
    "chairs",
}
CHAIR_FIELDS = {
    "seat",
    "occupant_name",
    "occupant_kind",
    "is_mine",
    "ready",
    "total",
    "is_away",
    "is_turn",
    "hold_seconds_left",
}
EMPTY = {"tables": []}
HEARTBEAT_LINE = ": "
HEARTBEATS_AWAITED = 10


def next_event(lines, named="mine"):
    """The next event of a response's lines with the given name as (name, decoded data), past any heartbeat comment
    and any event of another name.
    """
    while True:
        line = next(lines)
        if line == HEARTBEAT_LINE:
            assert next(lines) == ""
            continue
        name = line.removeprefix("event: ")
        data = json.loads(next(lines).removeprefix("data: "))
        assert next(lines) == ""
        if name == named:
            return name, data


class TestTheRoute:
    def test_signed_out_gets_no_stream_and_no_data(self, skat):
        answer = skat.client.get(LOBBY_EVENTS_PATH, headers=FETCH)

        assert (answer.status_code, "tables" in answer.text, "event: open" in answer.text) == (401, False, False)

    def test_an_agents_bearer_token_gets_no_stream(self, skat, agent, issuer):
        agent.admitted()
        skat.client.cookies.clear()

        answer = skat.client.get(
            LOBBY_EVENTS_PATH, headers={"authorization": f"Bearer {issuer.agent_token(SUBJECT)}", **FETCH}
        )

        assert answer.status_code in {401, 403}
        assert "tables" not in answer.text

    def test_a_member_without_a_chair_gets_mine_with_an_empty_list_and_a_comment_line_per_heartbeat(self, hold, issuer):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        headers, _ = skat.member()
        skat.client.cookies.clear()

        with skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=headers) as answer:
            lines = answer.iter_lines()
            read = [next(lines) for _ in range(8)]
            answer.close()

        assert (answer.status_code, answer.headers["content-type"], answer.headers["cache-control"]) == (
            200,
            "text/event-stream; charset=utf-8",
            "no-store",
        )
        assert read == [
            "event: mine",
            'data: {"tables":[]}',
            "",
            "event: open",
            'data: {"tables":[]}',
            "",
            ": ",
            "",
        ]

    def test_a_table_opened_and_one_sat_at_through_the_routes_reach_the_open_lobbies_of_their_accounts_and_no_stranger(
        self, tables_skat
    ):
        skat = tables_skat
        annas_headers, anna = skat.member()
        bens_headers, ben = skat.member()
        strangers_headers, stranger = skat.member()
        skat.client.cookies.clear()

        with (
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=annas_headers) as annas,
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=bens_headers) as bens,
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=strangers_headers) as strangers,
        ):
            annas_lines, bens_lines, strangers_lines = annas.iter_lines(), bens.iter_lines(), strangers.iter_lines()
            firsts = [next_event(lines) for lines in (annas_lines, bens_lines, strangers_lines)]
            skat.client.cookies.clear()
            table_id = skat.create(annas_headers).json()["id"]
            _, opened = next_event(annas_lines)
            skat.client.cookies.clear()
            skat.sit(bens_headers, table_id, 2)
            _, named = next_event(annas_lines)
            _, sat = next_event(bens_lines)
            strangers_seen = [next(strangers_lines) for _ in range(HEARTBEATS_AWAITED * 2)]
            skat.stores.sessions.delete_for_user(stranger.id)
            strangers_seen += list(strangers_lines)
            annas.close()
            bens.close()

        assert firsts == [("mine", EMPTY)] * 3
        assert "event: mine" not in strangers_seen
        assert ids_of(opened["tables"]) == [table_id]
        assert [chair["occupant_name"] for chair in named["tables"][0]["chairs"]] == [anna.username, ben.username, None]
        assert (sat["tables"][0]["id"], [chair["is_mine"] for chair in sat["tables"][0]["chairs"]]) == (
            table_id,
            [False, True, False],
        )

    def test_a_table_opened_private_through_the_route_reaches_only_its_opener_and_an_open_one_every_member(
        self, tables_skat
    ):
        skat = tables_skat
        annas_headers, _ = skat.member()
        bens_headers, _ = skat.member()
        skat.client.cookies.clear()

        with (
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=annas_headers) as annas,
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=bens_headers) as bens,
        ):
            annas_lines, bens_lines = annas.iter_lines(), bens.iter_lines()
            for lines in (annas_lines, bens_lines):
                next_event(lines)
                next_event(lines, "open")
            skat.client.cookies.clear()
            hidden = skat.create(annas_headers, command_id="command-private", visibility="private").json()["id"]
            _, annas_mine = next_event(annas_lines)
            skat.client.cookies.clear()
            listed = skat.create(annas_headers, command_id="command-open").json()["id"]
            _, bens_open = next_event(bens_lines, "open")
            annas.close()
            bens.close()

        assert [(entry["id"], entry["private"]) for entry in annas_mine["tables"]] == [(hidden, True)]
        assert ids_of(bens_open["tables"]) == [listed]

    def test_no_message_carries_a_card_a_card_count_or_the_account_of_anybody(self, skat):
        people = [skat.member() for _ in range(3)]
        table_id = skat.create(people[0][0]).json()["id"]
        for seat, (headers, _) in enumerate(people[1:], start=2):
            skat.sit(headers, table_id, seat, command_id=f"command-sit-{seat}")
        skat.client.cookies.clear()

        with skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=people[0][0]) as answer:
            lines = answer.iter_lines()
            next(lines)
            message = next(lines)
            answer.close()

        entry = json.loads(message.removeprefix("data: "))["tables"][0]
        assert set(entry) == ENTRY_FIELDS
        assert all(set(chair) == CHAIR_FIELDS for chair in entry["chairs"])
        assert not {account.id for _, account in people} & set(message.replace('"', " ").split())

    def test_a_second_tab_gets_every_mine_and_closing_one_leaves_the_other_open(self, skat):
        headers, _ = skat.member()
        skat.client.cookies.clear()

        with (
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=headers) as one,
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=headers) as another,
        ):
            tabs = [one.iter_lines(), another.iter_lines()]
            firsts = [next_event(lines) for lines in tabs]
            one.close()
            skat.client.cookies.clear()
            table_id = skat.create(headers).json()["id"]
            _, changed = next_event(tabs[1])
            another.close()

        assert firsts == [("mine", EMPTY)] * 2
        assert ids_of(changed["tables"]) == [table_id]

    def test_a_session_ended_server_side_ends_the_stream_at_the_next_heartbeat(self, hold, issuer):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        headers, member = skat.member()
        skat.client.cookies.clear()

        with skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=headers) as answer:
            lines = answer.iter_lines()
            first = [next(lines) for _ in range(6)]
            skat.stores.sessions.delete_for_user(member.id)
            rest = list(lines)

        assert first[0] == "event: mine"
        assert not any(line.startswith("event") for line in rest)
