import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

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
    from skat.web.presence import Presence

EVENT_STREAM: Final = "text/event-stream"
# A comment line is ignored by every event source; it keeps an idle stream's bytes moving past an edge's read timeout.
HEARTBEAT_COMMENT: Final = ": \n\n"


@dataclass(frozen=True)
class IdleHeartbeat:
    """What a stream yields for a heartbeat that passed with no change to send: a comment line, no view."""


IDLE_HEARTBEAT: Final = IdleHeartbeat()


def _message_of(item: TableView | IdleHeartbeat) -> str:
    if isinstance(item, IdleHeartbeat):
        return HEARTBEAT_COMMENT
    return f"data: {answer_of(item).model_dump_json()}\n\n"


async def _ask_for_next_deal(presence: Presence, table_id: str, view: TableView) -> None:
    if view.passed_in is not None:
        presence.deal_soon(table_id)
    if view.result is not None:
        await presence.deal_now(table_id)


async def _wait_for_change_or_heartbeat(changed: asyncio.Event, heartbeat_seconds: float) -> bool:
    """Wait until a change is set or one heartbeat passes idle; true when the heartbeat passed idle."""
    heartbeat_read = False
    while not changed.is_set() and not heartbeat_read:
        with suppress(TimeoutError):
            await asyncio.wait_for(changed.wait(), heartbeat_seconds)
        heartbeat_read = not changed.is_set()
    return heartbeat_read


async def table_views(
    presence: Presence,
    read_view: Callable[[Actor, frozenset[str]], Awaitable[TableView | None]],
    admit: Callable[[], Awaitable[Actor | None]],
    table_id: str,
    account_id: str,
    *,
    heartbeat_seconds: float,
) -> AsyncIterator[TableView | IdleHeartbeat]:
    """The views one stream sends: the full view first, then a fresh one after each change.

    The stream registers before it reads, so a change after registering is never lost. Changes that pile up
    while the consumer is slow fold into one wake and one fresh read, so a slow consumer holds no queue
    and delays no other stream. The session is admitted again before every view and on every idle
    heartbeat; the stream ends, sending nothing more, when `admit` refuses or the presence stops. Each idle
    heartbeat reads the view again and sends it only when the table's version moved since the last view
    sent, which recovers a lost wake; an unchanged one yields the idle heartbeat instead. A stream's first view
    of a passed-in table asks for the next deal, so a member's return, a restart or a lost deal starts a fresh
    pause; its first view of a pending result asks for the deal at once, and the marks decide. A stream that
    finds its table ended sends that view as its last.
    """
    changed = asyncio.Event()
    subscription = await presence.subscribe(table_id, account_id, changed.set)
    sent_version: int | None = None
    heartbeat_read = False
    try:
        while True:
            changed.clear()
            # A stop that lands during the admission has set `changed`, so the check follows the call.
            actor = await admit()
            if actor is None or presence.stopped:
                return
            view = await read_view(actor, presence.connected(table_id))
            if view is None:
                message = f"table {table_id} vanished while a stream watched it"
                raise RuntimeError(message)
            if view.ended is not None:
                yield view
                return
            if sent_version is None:
                await _ask_for_next_deal(presence, table_id, view)
            if heartbeat_read and view.version == sent_version:
                yield IDLE_HEARTBEAT
            else:
                yield view
                sent_version = view.version
            heartbeat_read = await _wait_for_change_or_heartbeat(changed, heartbeat_seconds)
    finally:
        presence.unsubscribe(subscription)


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

        async def messages() -> AsyncIterator[str]:
            # An ended table has nobody to watch: its one message is its answer, and nothing registers.
            if first_view.ended is not None:
                yield _message_of(first_view)
                return
            async for item in table_views(
                presence, read_view, admit, table_id, opened_as.account_id, heartbeat_seconds=heartbeat_seconds
            ):
                yield _message_of(item)

        return StreamingResponse(
            messages(), media_type=EVENT_STREAM, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        )

    return router
