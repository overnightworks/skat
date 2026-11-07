import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from skat.table.records import Actor, CreateTable, TableId
from skat.table.service import TableService
from skat.web.presence import Presence
from skat.web.streams import table_views
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.web.support.skat import FETCH, UNKNOWN_ID

OPENER = Actor(account_id="opener", display_name="Anna")
VISITOR = Actor(account_id="visitor", display_name="Ben")
ALLOWED_SECONDS = 2


@pytest.fixture
def service():
    return TableService(FakeTableStore(), new_table_id=lambda: TableId("1" * 32))


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-1")).id


def reader(service, actor, table_id):
    async def read_view(connected):
        return service.view(actor, table_id, connected)

    return read_view


def stream_of(presence, service, actor, table_id):
    return table_views(presence, reader(service, actor, table_id), table_id, actor.account_id)


def run_on_a_loop_of_its_own(scenario):
    """A thread of its own keeps the loop apart from one that a browser driver left running in this one."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, scenario).result()


async def next_view(stream):
    return await asyncio.wait_for(anext(stream), ALLOWED_SECONDS)


class TestTableViews:
    def test_the_first_view_is_the_full_view_and_a_change_brings_a_fresh_one_at_the_same_version(
        self, service, table_id
    ):
        async def scenario():
            presence = Presence()
            stream = stream_of(presence, service, OPENER, table_id)
            first = await next_view(stream)
            visitor = presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            joined = await next_view(stream)
            presence.unsubscribe(visitor)
            left = await next_view(stream)
            await stream.aclose()
            return first, joined, left, presence

        first, joined, left, presence = run_on_a_loop_of_its_own(scenario())

        assert [(view.watchers, view.version) for view in (first, joined, left)] == [(0, 1), (1, 1), (0, 1)]
        assert presence.connected(table_id) == frozenset()

    def test_the_stream_registers_before_it_reads_so_a_change_during_the_read_is_not_lost(self, service, table_id):
        async def scenario():
            presence = Presence()
            read_view = reader(service, VISITOR, table_id)
            reads = []

            async def read_while_another_connects(connected):
                reads.append(connected)
                if len(reads) == 1:
                    presence.subscribe(table_id, "late", lambda: None)
                return await read_view(connected)

            stream = table_views(presence, read_while_another_connects, table_id, VISITOR.account_id)
            first = await next_view(stream)
            second = await next_view(stream)
            await stream.aclose()
            return first, second

        first, second = run_on_a_loop_of_its_own(scenario())

        assert (first.watchers, second.watchers) == (1, 2)

    def test_each_stream_gets_the_view_built_for_its_own_account(self, service, table_id):
        async def scenario():
            presence = Presence()
            opener_stream = stream_of(presence, service, OPENER, table_id)
            visitor_stream = stream_of(presence, service, VISITOR, table_id)
            views = await next_view(opener_stream), await next_view(visitor_stream)
            await opener_stream.aclose()
            await visitor_stream.aclose()
            return views

        opener_view, visitor_view = run_on_a_loop_of_its_own(scenario())

        assert [chair.is_mine for chair in opener_view.chairs] == [True, False, False]
        assert [chair.is_mine for chair in visitor_view.chairs] == [False, False, False]

    def test_a_stalled_stream_delays_nobody_and_catches_up_with_one_fresh_view(self, service, table_id):
        async def scenario():
            presence = Presence()
            stalled = stream_of(presence, service, OPENER, table_id)
            await next_view(stalled)
            quick = stream_of(presence, service, VISITOR, table_id)
            await next_view(quick)
            seen_by_quick = []
            for number in range(5):
                guest = presence.subscribe(table_id, f"guest-{number}", lambda: None)
                seen_by_quick.append((await next_view(quick)).watchers)
                presence.unsubscribe(guest)
                await next_view(quick)
            caught_up = await next_view(stalled)
            await stalled.aclose()
            await quick.aclose()
            return seen_by_quick, caught_up

        seen_by_quick, caught_up = run_on_a_loop_of_its_own(scenario())

        assert seen_by_quick == [2] * 5
        assert caught_up.watchers == 1

    def test_the_stream_ends_when_its_table_is_gone(self, table_id):
        async def vanished(_connected):
            return None

        async def scenario():
            presence = Presence()
            stream = table_views(presence, vanished, table_id, OPENER.account_id)
            with pytest.raises(StopAsyncIteration):
                await anext(stream)
            return presence

        assert run_on_a_loop_of_its_own(scenario()).connected(table_id) == frozenset()


class TestWatchTableAdmission:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def test_signed_out_gets_no_stream_and_no_table_data(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.get(self.events(table_id), headers=FETCH)

        assert answer.status_code == 401
        assert table_id not in answer.text

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "%27%3B--", "A" * 32])
    def test_an_unknown_or_malformed_id_is_not_found_and_holds_nothing_open(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.client.get(self.events(table_id), headers=headers)

        assert (answer.status_code, answer.json()) == (404, {"detail": "table not found"})

    def test_a_member_gets_the_full_view_of_the_table_as_the_first_event(self, skat):
        opener_headers, opener = skat.member()
        table = skat.create(opener_headers).json()
        watcher_headers, watcher = skat.member()
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table["id"]), headers=watcher_headers) as answer:
            lines = iter(answer.iter_lines())
            first = next(lines)
            second = next(lines)
            answer.close()

        assert (answer.status_code, answer.headers["content-type"], answer.headers["cache-control"]) == (
            200,
            "text/event-stream; charset=utf-8",
            "no-store",
        )
        event = json.loads(first.removeprefix("data: "))
        assert second == ""
        assert (event["id"], event["version"], event["watchers"]) == (table["id"], 1, 1)
        assert [chair["is_mine"] for chair in event["chairs"]] == [False, False, False]
        assert watcher.id not in first
        assert opener.id not in first
