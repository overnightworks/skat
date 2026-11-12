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
    from collections.abc import AsyncIterator, Awaitable, Callable

    from webauth.ports import SessionRecordStore

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


def _message_of(item: SourceMessage | IdleHeartbeat) -> str:
    if isinstance(item, IdleHeartbeat):
        return HEARTBEAT_COMMENT
    named = "" if item.event is None else f"event: {item.event}\n"
    return f"{named}data: {item.data}\n\n"


def _table_message(view: TableView) -> SourceMessage:
    return SourceMessage(answer_of(view).model_dump_json(), last=view.ended is not None)


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
        view = await self._read_view(actor, self._presence.connected(self._table_id))
        if view is None:
            message = f"table {self._table_id} vanished while a stream watched it"
            raise RuntimeError(message)
        if self._first_read and view.ended is None:
            await self._ask_for_next_deal(view)
        self._first_read = False
        return _table_message(view)

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


async def stream_messages(
    source: StreamSource,
    admit: Callable[[], Awaitable[Actor | None]],
    stopped: Callable[[], bool],
    *,
    heartbeat_seconds: float,
) -> AsyncIterator[SourceMessage | IdleHeartbeat]:
    """The items one stream sends: the source's whole state first, then a fresh one after each change.

    The stream opens the source before it reads, so a change after opening is never lost. Wakes that pile up
    while the consumer is slow fold into one wake and one fresh read, so a slow consumer holds no queue and
    delays no other stream. The session is admitted again before every read; the stream ends, sending nothing
    more, when `admit` refuses or `stopped` holds, and `stopped` is read after the admission because a stop
    during it has already set the wake. A read is sent only when it differs from the last one sent, so a wake
    that changes nothing sends nothing. A heartbeat deadline counts from the last item yielded; when it
    passes, the stream reads again, which recovers a lost wake, and yields the idle heartbeat unless that read
    differs. A `last` message ends the stream after it.
    """
    changed = asyncio.Event()
    await source.open(changed.set)
    loop = asyncio.get_running_loop()
    try:
        sent_digest: bytes | None = None
        deadline = loop.time() + heartbeat_seconds
        deadline_passed = False
        while True:
            changed.clear()
            # A stop that lands during the admission has set `changed`, so the check follows the call.
            actor = await admit()
            if actor is None or stopped():
                return
            message = await source.read(actor)
            digest = _digest_of(message)
            if digest != sent_digest:
                sent_digest = digest
                yield message
                if message.last:
                    return
                deadline = loop.time() + heartbeat_seconds
            elif deadline_passed:
                yield IDLE_HEARTBEAT
                deadline = loop.time() + heartbeat_seconds
            deadline_passed = await _wait_for_wake_or_deadline(changed, deadline)
    finally:
        source.close()


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
    tables: TableService, presence: Presence, sessions: SessionRecordStore, heartbeat_seconds: float
) -> APIRouter:
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
                yield _message_of(_table_message(first_view))
                return
            source = TableSource(presence, read_view, table_id, opened_as.account_id)
            async for item in stream_messages(
                source, admit, lambda: presence.stopped, heartbeat_seconds=heartbeat_seconds
            ):
                yield _message_of(item)

        return StreamingResponse(
            messages(), media_type=EVENT_STREAM, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        )

    return router
