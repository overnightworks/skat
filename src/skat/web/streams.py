import asyncio
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH, actor_of, answer_of

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from skat.table.service import TableService
    from skat.table.views import TableView
    from skat.web.presence import Presence

EVENT_STREAM: Final = "text/event-stream"


async def table_views(
    presence: Presence,
    read_view: Callable[[frozenset[str]], Awaitable[TableView | None]],
    table_id: str,
    account_id: str,
) -> AsyncIterator[TableView]:
    """The views one stream sends: the full view first, then a fresh one after each change.

    The stream registers before it reads, so a change after registering is never lost. Changes that pile up
    while the consumer is slow fold into one wake and one fresh read, so a slow consumer holds no queue
    and delays no other stream.
    """
    changed = asyncio.Event()
    subscription = presence.subscribe(table_id, account_id, changed.set)
    try:
        while True:
            changed.clear()
            view = await read_view(presence.connected(table_id))
            if view is None:
                message = f"table {table_id} vanished while a stream watched it"
                raise RuntimeError(message)
            yield view
            await changed.wait()
    finally:
        presence.unsubscribe(subscription)


def create_streams_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_EVENTS_SUFFIX,
        response_class=StreamingResponse,
        responses={404: {"description": "No table has this id."}},
    )
    async def watch_table(table_id: str, request: Request) -> StreamingResponse:
        actor = actor_of(request)

        async def read_view(connected: frozenset[str]) -> TableView | None:
            return await run_in_threadpool(tables.view, actor, table_id, connected)

        # Nothing is registered or held open for an id that is no table.
        if await read_view(frozenset()) is None:
            raise HTTPException(status_code=404, detail="table not found")

        async def messages() -> AsyncIterator[str]:
            async for view in table_views(presence, read_view, table_id, actor.account_id):
                yield f"data: {answer_of(view).model_dump_json()}\n\n"

        return StreamingResponse(
            messages(), media_type=EVENT_STREAM, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        )

    return router
