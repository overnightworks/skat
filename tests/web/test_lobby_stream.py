"""The lobby stream sends an account the tables it holds a chair at, and no other, as the named event `mine`."""

import asyncio
import json
from contextlib import nullcontext

import pytest

from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, SitDown, TableId, Visibility
from skat.table.service import TableService
from skat.web.lobby import LOBBY_EVENTS_PATH
from skat.web.streams import IDLE_HEARTBEAT, SourceMessage, StreamEvent
from skat.web.wakes import AccountTopic
from tests.support.fake_tables import FakeTableStore
from tests.web.support.agent import SUBJECT
from tests.web.support.lobby_scene import Scene
from tests.web.support.skat import FETCH, Skat
from tests.web.support.streams import (
    SHORT_HEARTBEAT_SECONDS,
    Admission,
    next_item,
    run_on_a_loop_of_its_own,
)

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")


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


async def next_mine(stream):
    """The tables of the next `mine`; fails on any other item."""
    item = await next_item(stream)
    assert isinstance(item, SourceMessage)
    assert item.event is StreamEvent.MINE
    return json.loads(item.data)["tables"]


async def next_open(stream):
    """The tables of the next `open`; fails on any other item."""
    item = await next_item(stream)
    assert isinstance(item, SourceMessage)
    assert item.event is StreamEvent.OPEN
    return json.loads(item.data)["tables"]


def ids_of(entries):
    return [entry["id"] for entry in entries]


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


class TestTheOpenList:
    def test_a_member_with_no_chair_gets_the_open_tables_with_their_free_chairs_and_the_opener_gets_none_of_his_own(
        self,
    ):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            bens, annas = scene.open_stream(BEN), scene.open_stream(ANNA)
            seen = await next_open(bens), await next_open(annas)
            await bens.aclose()
            await annas.aclose()
            return seen

        bens, annas = run_on_a_loop_of_its_own(scenario())

        assert (ids_of(bens), [chair["occupant_name"] for chair in bens[0]["chairs"]], bens[0]["free_chairs"]) == (
            [table_id],
            ["Anna", None, None],
            2,
        )
        assert annas == []

    def test_a_private_table_is_in_no_open_list_and_in_the_opener_s_mine_with_a_lock(self):
        scene = Scene()
        table_id = scene.open_table(ANNA, Visibility.PRIVATE)

        async def scenario():
            bens, annas = scene.open_stream(BEN), scene.stream(ANNA)
            seen = await next_open(bens), await next_mine(annas)
            await bens.aclose()
            await annas.aclose()
            return seen

        bens, annas = run_on_a_loop_of_its_own(scenario())

        assert (bens, [(entry["id"], entry["private"]) for entry in annas]) == ([], [(table_id, True)])

    def test_a_private_table_stays_out_of_the_open_list_after_a_sit_and_a_deal(self):
        scene = Scene()
        table_id = scene.open_table(ANNA, Visibility.PRIVATE)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)

        async def scenario():
            strangers, annas, bens = scene.open_stream(DORA), scene.stream(ANNA), scene.stream(BEN)
            seen = await next_open(strangers), await next_mine(annas), await next_mine(bens)
            await strangers.aclose()
            await annas.aclose()
            await bens.aclose()
            return seen

        strangers, annas, bens = run_on_a_loop_of_its_own(scenario())

        assert (strangers, [entry["private"] for entry in annas], [entry["private"] for entry in bens]) == (
            [],
            [True],
            [True],
        )

    def test_an_open_table_is_not_marked_private_in_mine(self):
        scene = Scene()
        scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(ANNA)
            mine = await next_mine(stream)
            await stream.aclose()
            return mine

        assert [entry["private"] for entry in run_on_a_loop_of_its_own(scenario())] == [False]

    def test_the_list_follows_a_table_opened_a_sit_a_stand_up_a_close_and_an_end(self):
        scene = Scene()

        async def scenario():
            stream = scene.open_stream(CLEO)
            seen = [await next_open(stream)]
            table_id = scene.open_table(ANNA)
            seen.append(await next_open(stream))
            scene.sit(BEN, table_id, 2)
            seen.append(await next_open(stream))
            scene.stand(BEN, table_id)
            seen.append(await next_open(stream))
            scene.close(ANNA, table_id)
            seen.append(await next_open(stream))
            ended = scene.open_table(ANNA)
            seen.append(await next_open(stream))
            assert scene.service.end_empty_table(TableId(ended), nullcontext(frozenset()), 0)
            scene.presence.wake_table(ended)
            seen.append(await next_open(stream))
            await stream.aclose()
            return table_id, ended, seen

        table_id, ended, seen = run_on_a_loop_of_its_own(scenario())

        assert [ids_of(tables) for tables in seen] == [[], [table_id], [table_id], [table_id], [], [ended], []]
        assert [[chair["occupant_name"] for chair in tables[0]["chairs"]] for tables in seen[1:4]] == [
            ["Anna", None, None],
            ["Anna", "Ben", None],
            ["Anna", None, None],
        ]

    def test_a_table_a_member_sits_at_leaves_his_open_list_and_joins_his_mine(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            open_list, mine = scene.open_stream(BEN), scene.stream(BEN)
            before = await next_open(open_list), await next_mine(mine)
            scene.sit(BEN, table_id, 2)
            after = await next_open(open_list), await next_mine(mine)
            await open_list.aclose()
            await mine.aclose()
            return before, after

        before, after = run_on_a_loop_of_its_own(scenario())

        assert ([ids_of(each) for each in before], [ids_of(each) for each in after]) == (
            [[table_id], []],
            [[], [table_id]],
        )

    def test_a_table_with_a_free_chair_is_listed_before_a_full_one(self):
        scene = Scene()
        full = scene.open_table(ANNA)
        scene.sit(BEN, full, 2)
        scene.sit(CLEO, full, 3)
        free = scene.open_table(ANNA)

        async def scenario():
            stream = scene.open_stream(Actor(account_id="account-dora", display_name="Dora"))
            listed = await next_open(stream)
            await stream.aclose()
            return listed

        listed = run_on_a_loop_of_its_own(scenario())

        assert [(entry["id"], entry["free_chairs"]) for entry in listed] == [(free, 2), (full, 0)]

    def test_an_away_member_at_an_undealt_open_table_shows_the_seconds_left_of_the_hold_from_presence(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.presence.hold_chairs([(table_id, ANNA.account_id)])

        async def scenario():
            stream = scene.open_stream(BEN)
            listed = await next_open(stream)
            await stream.aclose()
            return listed

        (entry,) = run_on_a_loop_of_its_own(scenario())

        assert [(chair["is_away"], chair["hold_seconds_left"]) for chair in entry["chairs"]] == [
            (True, 300),
            (False, None),
            (False, None),
        ]

    def test_the_open_entry_carries_the_series_the_options_and_the_watchers_and_no_card_or_account(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            await scene.presence.subscribe(table_id, CLEO.account_id, lambda: None)
            stream = scene.open_stream(BEN)
            listed = await next_open(stream)
            await stream.aclose()
            return listed

        (entry,) = run_on_a_loop_of_its_own(scenario())

        assert set(entry) == OPEN_ENTRY_FIELDS
        assert all(set(chair) == OPEN_CHAIR_FIELDS for chair in entry["chairs"])
        assert (entry["id"], entry["watchers"], entry["options"]["show_running_points"]) == (table_id, 1, False)
        assert CLEO.account_id not in json.dumps(entry)


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

    def tables_held_by(self, account_id):
        held = super().tables_held_by(account_id)
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
OPEN_ENTRY_FIELDS = {
    "id",
    "title_name",
    "game_number",
    "game_count",
    "options",
    "watchers",
    "free_chairs",
    "dealt",
    "waiting_seat",
    "ends_at",
    "chairs",
}
OPEN_CHAIR_FIELDS = {"seat", "occupant_name", "occupant_kind", "is_away", "hold_seconds_left"}


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
