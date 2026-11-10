import json
from contextlib import nullcontext

import pytest

from skat.table.records import CreateTable, EndReason, TableId
from skat.web.presence import EmptyTable, Presence
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.fake_tables import in_memory_tables
from tests.support.idle_presence import (
    end_no_table,
    idle_agent_lease,
    idle_hold,
    idle_next_deal,
    idle_presence,
)
from tests.web.support.streams import OPENER, VISITOR, next_view, run_on_a_loop_of_its_own, stream_of


def end_for_nobody(service, table_id):
    return service.end_empty_table(TableId(table_id), nullcontext(frozenset()), DEFAULT_EMPTY_TABLE_SECONDS)


@pytest.fixture
def service():
    return in_memory_tables()


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-1")).id


class TestAStreamOnAnEndingTable:
    def test_a_stream_whose_table_ends_sends_the_ended_view_and_then_stops(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, VISITOR, table_id)
            live = await next_view(stream)
            end_for_nobody(service, table_id)
            presence.wake_table(table_id)
            ended = await next_view(stream)
            with pytest.raises(StopAsyncIteration):
                await next_view(stream)
            return live, ended, presence.connected(table_id)

        live, ended, connected = run_on_a_loop_of_its_own(scenario())

        assert live.ended is None
        assert (ended.ended.reason, ended.ended.empty_seconds) == (EndReason.EMPTY, DEFAULT_EMPTY_TABLE_SECONDS)
        assert ended.version == live.version + 1
        assert connected == frozenset()

    def test_a_stream_that_reads_an_ended_table_first_sends_it_and_stops(self, service, table_id):
        end_for_nobody(service, table_id)

        async def scenario():
            stream = stream_of(idle_presence(), service, VISITOR, table_id)
            ended = await next_view(stream)
            with pytest.raises(StopAsyncIteration):
                await next_view(stream)
            return ended

        assert run_on_a_loop_of_its_own(scenario()).ended is not None


class TestTheStreamRoute:
    def test_an_ended_tables_stream_sends_one_message_without_chairs_and_ends(self, server, time, hold):
        headers, _ = server.member()
        table_id = server.create(headers).json()["id"]
        server.client.portal.call(time.advance, hold.settings.empty_table_seconds)

        with server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=headers) as s:
            lines = [line for line in s.iter_lines() if line.startswith("data: ")]

        assert len(lines) == 1
        assert time.pending == 0
        message = json.loads(lines[0].removeprefix("data: "))
        assert message["ended"] == {"reason": "empty", "empty_seconds": hold.settings.empty_table_seconds}
        assert (message["chairs"], message["hand"], message["result"], message["watchers"]) == ([], None, None, 0)


class TestAStreamWhoseArrivalWriteFails:
    def test_it_sends_nothing_and_fails_without_a_message_while_a_retry_writes_again(self, service, table_id):
        calls = []

        async def note(table, connected_accounts):
            calls.append(table)
            if len(calls) == 1:
                raise ConnectionError
            return False

        empty_table = EmptyTable(DEFAULT_EMPTY_TABLE_SECONDS, end_no_table, note)
        presence = Presence(idle_hold(), idle_next_deal(), empty_table, idle_agent_lease())

        async def scenario():
            failed = stream_of(presence, service, VISITOR, table_id)
            with pytest.raises(ConnectionError):
                await next_view(failed)
            return await next_view(stream_of(presence, service, VISITOR, table_id))

        retried = run_on_a_loop_of_its_own(scenario())

        assert (len(calls), retried.ended) == (2, None)
