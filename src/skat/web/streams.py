import asyncio
import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from webauth.config import installed_web_auth_config
from webauth.dependencies import ConnectionRefusal, admit_session, session_id_from_request

from skat.web.mcp import Exclusion, excluded
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH, actor_for, actor_of, answer_of

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence

    from webauth.ports import SessionRecordStore

    from skat.table.nudging import NudgeState
    from skat.table.records import Actor
    from skat.table.service import TableService
    from skat.table.views import TableView
    from skat.web.presence import Presence, Subscription

EVENT_STREAM: Final = "text/event-stream"
# A comment line is ignored by every event source; it keeps an idle stream's bytes moving past an edge's read timeout.
HEARTBEAT_COMMENT: Final = ": \n\n"


@dataclass(frozen=True)
class IdleHeartbeat:
    """What a stream yields for a heartbeat that passed with no change to send: a comment line, no view."""


IDLE_HEARTBEAT: Final = IdleHeartbeat()


class StreamEvent(StrEnum):
    """The names a stream gives its events; a client listens by name."""

    MINE = "mine"
    OPEN = "open"
    ATTENTION = "attention"


@dataclass(frozen=True)
class SourceMessage:
    """The whole state of one source as the stream sends it, under the event's name when it has one; `last` ends the
    stream after it.
    """

    data: str
    event: StreamEvent | None = None
    last: bool = False


class StreamSource(Protocol):  # pragma: no cover - a port's method bodies are signatures; the sources run
    async def open(self, wake: Callable[[], None]) -> None:
        """Register `wake` for every change of this source's state; the stream reads only after this returns."""
        ...

    async def read(self, actor: Actor) -> SourceMessage:
        """The whole state for `actor`."""
        ...

    def close(self) -> None: ...


def message_of(item: SourceMessage | IdleHeartbeat) -> str:
    if isinstance(item, IdleHeartbeat):
        return HEARTBEAT_COMMENT
    named = "" if item.event is None else f"event: {item.event}\n"
    return f"{named}data: {item.data}\n\n"


def _table_message(view: TableView, nudges: Mapping[int, NudgeState]) -> SourceMessage:
    return SourceMessage(answer_of(view, nudges).model_dump_json(), last=view.ended is not None)


class TableSource:
    """The table view of one account as a stream source: it asks for the next deal with its first view."""

    def __init__(
        self,
        presence: Presence,
        read_view: Callable[[Actor, frozenset[str]], Awaitable[TableView | None]],
        table_id: str,
        account_id: str,
    ) -> None:
        self._presence = presence
        self._read_view = read_view
        self._table_id = table_id
        self._account_id = account_id
        self._subscription: Subscription | None = None
        self._first_read = True

    async def open(self, wake: Callable[[], None]) -> None:
        self._subscription = await self._presence.subscribe(self._table_id, self._account_id, wake)

    async def read(self, actor: Actor) -> SourceMessage:
        with self._presence.waits.reading(self._table_id):
            view = await self._read_view(actor, self._presence.connected(self._table_id))
            if view is None:
                message = f"table {self._table_id} vanished while a stream watched it"
                raise RuntimeError(message)
            nudges = self._presence.waits.nudges_of(view)
        if self._first_read and view.ended is None:
            await self._ask_for_next_deal(view)
        self._first_read = False
        return _table_message(view, nudges)

    def close(self) -> None:
        assert self._subscription is not None  # noqa: S101 - narrows the type; the loop closes only an opened source
        self._presence.unsubscribe(self._subscription)

    async def _ask_for_next_deal(self, view: TableView) -> None:
        if view.passed_in is not None:
            self._presence.deal_soon(self._table_id)
        if view.result is not None:
            await self._presence.deal_now(self._table_id)


def _digest_of(message: SourceMessage) -> bytes:
    return hashlib.blake2b(message.data.encode(), digest_size=16).digest()


async def _wait_for_wake_or_deadline(changed: asyncio.Event, deadline: float) -> bool:
    """Wait for a wake or the deadline; true once the deadline has passed."""
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(changed.wait(), max(deadline - loop.time(), 0))
    except TimeoutError:
        return True
    return loop.time() >= deadline


def _wake_of(index: int, unread: list[bool], changed: asyncio.Event) -> Callable[[], None]:
    def wake() -> None:
        unread[index] = True
        changed.set()

    return wake


async def _changed_messages(
    sources: Sequence[StreamSource],
    actor: Actor,
    unread: list[bool],
    sent_digests: list[bytes | None],
    *,
    read_all: bool,
) -> list[SourceMessage]:
    """The reads, in the sources' order, that differ from the last one sent; a `last` message is the final one."""
    changed: list[SourceMessage] = []
    for index, source in enumerate(sources):
        if not (unread[index] or read_all):
            continue
        unread[index] = False
        message = await source.read(actor)
        digest = _digest_of(message)
        if digest == sent_digests[index]:
            continue
        sent_digests[index] = digest
        changed.append(message)
        if message.last:
            break
    return changed


async def stream_messages(
    sources: Sequence[StreamSource],
    admit: Callable[[], Awaitable[Actor | None]],
    stopped: Callable[[], bool],
    *,
    heartbeat_seconds: float,
) -> AsyncIterator[SourceMessage | IdleHeartbeat]:
    """The items one stream sends: each source's whole state first, then a fresh one after each change of it.

    The stream opens a source before it reads it, so a change after opening is never lost. A wake marks its own
    source for a read, so a source is read only for a wake of its own or a heartbeat. Wakes that pile up while the
    consumer is slow fold into one fresh read per source, so a slow consumer holds no queue and delays no other
    stream. The session is admitted again before every round of reads; the stream ends, sending nothing more,
    when `admit` refuses or `stopped` holds, and `stopped` is read after the admission because a stop during it
    has already set the wake. A read is sent only when it differs from the last one sent of its source, so a wake
    that changes nothing sends nothing. A heartbeat deadline counts from the last item yielded; when it passes,
    every source is read again, which recovers a lost wake, and the idle heartbeat is yielded unless a read
    differs. A `last` message ends the stream after it, before the sources listed after its source are read.
    """
    changed = asyncio.Event()
    unread = [True] * len(sources)

    opened: list[StreamSource] = []
    loop = asyncio.get_running_loop()
    try:
        for index, source in enumerate(sources):
            await source.open(_wake_of(index, unread, changed))
            opened.append(source)
        sent_digests: list[bytes | None] = [None] * len(sources)
        deadline = loop.time() + heartbeat_seconds
        deadline_passed = False
        while True:
            changed.clear()
            # A stop that lands during the admission has set `changed`, so the check follows the call.
            actor = await admit()
            if actor is None or stopped():
                return
            changed_messages = await _changed_messages(sources, actor, unread, sent_digests, read_all=deadline_passed)
            for message in changed_messages:
                yield message
                if message.last:
                    return
            if changed_messages:
                deadline = loop.time() + heartbeat_seconds
            elif deadline_passed:
                yield IDLE_HEARTBEAT
                deadline = loop.time() + heartbeat_seconds
            deadline_passed = await _wait_for_wake_or_deadline(changed, deadline)
    finally:
        for source in opened:
            source.close()


def event_stream_response(messages: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        messages, media_type=EVENT_STREAM, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )


def session_admission(request: Request, sessions: SessionRecordStore) -> Callable[[], Awaitable[Actor | None]]:
    """The admission a stream repeats before every read: the actor of the request's session, None once it is refused."""
    # The gate admitted this request by its cookie, so a missing session id is a wiring fault.
    config = installed_web_auth_config(request.app)
    session_id = session_id_from_request(request, config)
    if session_id is None:  # pragma: no cover
        message = "A stream route ran without a session cookie."
        raise RuntimeError(message)

    async def admit() -> Actor | None:
        # Each admission is one call into the store, which takes its own guard; it renews the session.
        admission = await run_in_threadpool(admit_session, session_id, sessions=sessions, config=config)
        if isinstance(admission, ConnectionRefusal):
            return None
        return actor_for(admission)

    return admit


def create_streams_router(
    tables: TableService,
    presence: Presence,
    sessions: SessionRecordStore,
    heartbeat_seconds: float,
    attention_of: Callable[[str, str], StreamSource],
) -> APIRouter:
    """The table stream: the table view, then `attention_of(table_id, account_id)`, the count of the account's other
    tables that wait for it.
    """
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_EVENTS_SUFFIX,
        response_class=StreamingResponse,
        responses={404: {"description": "No table has this id."}},
        openapi_extra=excluded(Exclusion.LIVE_STREAM),
    )
    async def watch_table(table_id: str, request: Request) -> StreamingResponse:
        opened_as = actor_of(request)

        async def read_view(actor: Actor, connected: frozenset[str]) -> TableView | None:
            return await run_in_threadpool(tables.view, actor, table_id, connected)

        # Nothing is registered or held open for an id that is no table.
        first_view = await read_view(opened_as, frozenset())
        if first_view is None:
            raise HTTPException(status_code=404, detail="table not found")

        admit = session_admission(request, sessions)

        async def messages() -> AsyncIterator[str]:
            # An ended table has nobody to watch: its one message is its answer, and nothing registers.
            if first_view.ended is not None:
                yield message_of(_table_message(first_view, {}))
                return
            sources = [
                TableSource(presence, read_view, table_id, opened_as.account_id),
                attention_of(table_id, opened_as.account_id),
            ]
            async for item in stream_messages(
                sources, admit, lambda: presence.stopped, heartbeat_seconds=heartbeat_seconds
            ):
                yield message_of(item)

        return event_stream_response(messages())

    return router
