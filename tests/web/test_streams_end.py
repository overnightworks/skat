import json
from contextlib import nullcontext

import pytest
from structlog.testing import capture_logs

from skat.table.records import CreateTable, EndReason, TableId
from skat.web.lobby import LOBBY_EVENTS_PATH
from skat.web.presence import EmptyTable, Presence
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from skat.web.streams import IDLE_HEARTBEAT, SourceMessage, StreamKind, messages_with_end_log
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from skat.web.wakes import WakeList
from tests.support.fake_tables import in_memory_tables
from tests.support.idle_presence import (
    end_no_table,
    idle_agent_lease,
    idle_hold,
    idle_next_deal,
    idle_presence,
)
from tests.web.support.skat import Skat, streams_of, unnamed_lines
from tests.web.support.streams import (
    OPENER,
    SHORT_HEARTBEAT_SECONDS,
    VISITOR,
    next_view,
    run_on_a_loop_of_its_own,
    stream_of,
)


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
        assert message["ended"] == {
            "reason": "empty",
            "empty_seconds": hold.settings.empty_table_seconds,
            "unplayed_days": None,
            "closed_by_name": None,
        }
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
        presence = Presence(idle_hold(), idle_next_deal(), empty_table, idle_agent_lease(), WakeList())

        async def scenario():
            failed = stream_of(presence, service, VISITOR, table_id)
            with pytest.raises(ConnectionError):
                await next_view(failed)
            return await next_view(stream_of(presence, service, VISITOR, table_id))

        retried = run_on_a_loop_of_its_own(scenario())

        assert (len(calls), retried.ended) == (2, None)


class TestAnUnplayedEnd:
    DAYS = 1

    @pytest.fixture
    def unplayed(self, sign_in_settings, time):
        skat = Skat(
            lambda: sign_in_settings(paused_table_days=self.DAYS),
            now=time.moment,
            chair_clock=time.clock,
            chair_scheduler=time,
        )
        with skat.client:
            yield skat

    def test_an_open_page_and_the_old_link_say_that_nobody_played_for_the_days(self, unplayed, time):
        anna, ben, cleo = unplayed.member(), unplayed.member(), unplayed.member()
        table_id = unplayed.create(anna[0]).json()["id"]
        unplayed.sit(ben[0], table_id, 2, command_id="command-ben")
        unplayed.sit(cleo[0], table_id, 3, command_id="command-cleo")

        with streams_of(unplayed, table_id, [anna]) as (open_page,):
            unplayed.client.portal.call(time.advance, self.DAYS * 24 * 3600)
            message = next(open_page)

        old_link = unplayed.client.get(f"{TABLES_PATH}/{table_id}", headers=ben[0]).json()
        expected = {"reason": "unplayed", "empty_seconds": None, "unplayed_days": self.DAYS, "closed_by_name": None}
        assert (message["ended"], old_link["ended"]) == (expected, expected)
        assert (old_link["chairs"], old_link["hand"], old_link["watchers"]) == ([], None, 0)


class ProducerFailedError(Exception):
    pass


async def ended_table():
    yield SourceMessage("the end", last=True)


async def finishing():
    return
    yield  # pragma: no cover - makes this an async generator


async def failing():
    yield SourceMessage("one")
    raise ProducerFailedError


async def idle():
    yield IDLE_HEARTBEAT


def ended_lines(logs):
    return [log for log in logs if log["event"] == "stream_ended"]


class TestTheEndLogOfAStream:
    @pytest.mark.parametrize(
        ("items", "stopped", "reason", "error_type"),
        [
            pytest.param(ended_table, False, "ended_table", None, id="ended-table"),
            pytest.param(finishing, False, "refused", None, id="refused-admission"),
            pytest.param(idle, True, "shutdown", None, id="shutdown"),
        ],
    )
    def test_a_stream_that_ends_by_itself_logs_one_line_with_the_reason_it_ended(
        self, items, stopped, reason, error_type
    ):
        async def scenario():
            return [message async for message in messages_with_end_log(items(), lambda: stopped, StreamKind.LOBBY)]

        with capture_logs() as logs:
            run_on_a_loop_of_its_own(scenario())

        assert [(log["reason"], log["error_type"]) for log in ended_lines(logs)] == [(reason, error_type)]

    def test_a_stream_whose_producer_raises_logs_the_exception_type_and_passes_the_error_on(self):
        async def scenario():
            return [message async for message in messages_with_end_log(failing(), lambda: False, StreamKind.LOBBY)]

        with capture_logs() as logs, pytest.raises(ProducerFailedError):
            run_on_a_loop_of_its_own(scenario())

        assert [(log["reason"], log["error_type"]) for log in ended_lines(logs)] == [("error", "ProducerFailedError")]

    def test_a_stream_closed_from_outside_logs_a_client_gone(self):
        async def scenario():
            stream = messages_with_end_log(idle(), lambda: False, StreamKind.LOBBY)
            await anext(stream)
            await stream.aclose()

        with capture_logs() as logs:
            run_on_a_loop_of_its_own(scenario())

        assert [log["reason"] for log in ended_lines(logs)] == ["client_gone"]

    def test_the_line_names_the_kind_the_table_and_the_lifetime_and_nothing_a_stream_sent(self):
        async def scenario():
            stream = messages_with_end_log(ended_table(), lambda: False, StreamKind.TABLE, "table-id")
            return [message async for message in stream]

        with capture_logs() as logs:
            run_on_a_loop_of_its_own(scenario())

        [line] = ended_lines(logs)
        assert (line["kind"], line["table_id"], line["lifetime_seconds"] >= 0) == ("table", "table-id", True)
        assert "the end" not in str(line)
        assert set(line) == {"event", "log_level", "kind", "table_id", "reason", "error_type", "lifetime_seconds"}


class TestTheEndLogAtTheRoutes:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def test_an_ended_tables_stream_logs_one_ended_table_line_with_its_table_id(self, server, time, hold):
        headers, _ = server.member()
        table_id = server.create(headers).json()["id"]
        server.client.portal.call(time.advance, hold.settings.empty_table_seconds)

        with capture_logs() as logs, server.client.stream("GET", self.events(table_id), headers=headers) as answer:
            list(answer.iter_lines())

        assert [(log["kind"], log["table_id"], log["reason"]) for log in ended_lines(logs)] == [
            ("table", table_id, "ended_table")
        ]

    @pytest.mark.parametrize("kind", [StreamKind.TABLE, StreamKind.LOBBY])
    def test_a_stream_whose_session_ends_logs_one_refused_line(self, sign_in_settings, kind):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        headers, member = skat.member()
        table_id = skat.create(headers).json()["id"]
        skat.client.cookies.clear()
        path = LOBBY_EVENTS_PATH if kind is StreamKind.LOBBY else self.events(table_id)

        with capture_logs() as logs, skat.client.stream("GET", path, headers=headers) as answer:
            lines = unnamed_lines(answer.iter_lines())
            next(lines)
            skat.stores.sessions.delete_for_user(member.id)
            list(lines)

        assert [(log["kind"], log["reason"]) for log in ended_lines(logs)] == [(kind.value, "refused")]
