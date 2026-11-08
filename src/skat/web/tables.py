from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from webauth.middleware import admitted_user

from skat.table.records import Actor, CreateTable, Refusal, SitDown, StandUp
from skat.table.rules import CHAIRS_PER_TABLE
from skat.table.service import CommandIdReusedError
from skat.web.routes import READ_METHODS, built_page_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from webauth.ports import AuthenticatedUser

    from skat.table.service import SeatingResult, TableService
    from skat.table.views import TableView
    from skat.web.page_build import PageBuild
    from skat.web.presence import Presence

TABLES_PATH: Final = "/api/tables"
TABLE_PAGE_PREFIX: Final = "/t/"
# The live view of a table: `TABLES_PATH/{table_id}` plus this.
TABLE_EVENTS_SUFFIX: Final = "/events"
# The commands that change a table: `TABLES_PATH/{table_id}` plus one of these.
TABLE_SIT_SUFFIX: Final = "/sit"
TABLE_STAND_SUFFIX: Final = "/stand"
# The browser's `crypto.randomUUID()` writes 36 characters of this alphabet.
COMMAND_ID_PATTERN: Final = r"^[A-Za-z0-9_-]{8,64}$"


class CreateTableRequest(BaseModel):
    """A client names only its retry key: the opener's account and chair come from the session."""

    model_config = ConfigDict(extra="forbid")

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]


class SitDownRequest(CreateTableRequest):
    seat: Annotated[int, Field(strict=True, ge=1, le=CHAIRS_PER_TABLE)]


class SeatRefusal(BaseModel):
    """A seating command that changed nothing; `holder_name` names who sits in a chair that was taken."""

    reason: Refusal
    holder_name: str | None


class ChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    is_mine: bool
    is_away: bool


class TableAnswer(BaseModel):
    id: str
    version: int
    chairs: list[ChairAnswer]
    watchers: int


def answer_of(view: TableView) -> TableAnswer:
    return TableAnswer(
        id=view.id,
        version=view.version,
        chairs=[
            ChairAnswer(seat=c.seat, occupant_name=c.occupant_name, is_mine=c.is_mine, is_away=c.is_away)
            for c in view.chairs
        ],
        watchers=view.watchers,
    )


def actor_for(user: AuthenticatedUser) -> Actor:
    return Actor(account_id=user.id, display_name=user.username)


def actor_of(request: Request) -> Actor:
    user = admitted_user(request)
    # The gate refuses a request without a session before the route runs, so a missing user is a wiring fault.
    if user is None:  # pragma: no cover
        message = "A table route ran without an admitted user."
        raise RuntimeError(message)
    return actor_for(user)


SEATING_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    404: {"description": "No table has this id."},
    409: {
        "model": SeatRefusal,
        "description": "The command changed nothing, or its id came back with another request.",
    },
}


async def seating_answer(
    command: Callable[[frozenset[str]], SeatingResult | None], presence: Presence, table_id: str, response: Response
) -> Response | TableAnswer:
    """Run a sit or stand off the event loop; once it committed, wake the table's streams."""
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await run_in_threadpool(command, presence.connected(table_id))
    except CommandIdReusedError:
        raise HTTPException(status_code=409, detail="command id reused with another request") from None
    if result is None:
        raise HTTPException(status_code=404, detail="table not found")
    if result.refusal is not None:
        refusal = SeatRefusal(reason=result.refusal, holder_name=result.holder)
        return JSONResponse(refusal.model_dump(mode="json"), status_code=409, headers={"Cache-Control": "no-store"})
    presence.wake_table(table_id)
    return answer_of(result.view)


def create_tables_router(tables: TableService, page_build: PageBuild, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(TABLES_PATH, responses={409: {"description": "The command id came back with another request."}})
    def create_table(body: CreateTableRequest, request: Request, response: Response) -> TableAnswer:
        # The answer names people, so no cache may keep it past the gate.
        response.headers["Cache-Control"] = "no-store"
        try:
            return answer_of(tables.create(actor_of(request), CreateTable(command_id=body.command_id)))
        except CommandIdReusedError:
            raise HTTPException(status_code=409, detail="command id reused with another request") from None

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SIT_SUFFIX, response_model=TableAnswer, responses=SEATING_RESPONSES
    )
    async def sit_down(
        table_id: str, body: SitDownRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        command = SitDown(command_id=body.command_id, table_id=table_id, seat=body.seat)
        return await seating_answer(partial(tables.sit, actor_of(request), command), presence, table_id, response)

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_STAND_SUFFIX, response_model=TableAnswer, responses=SEATING_RESPONSES
    )
    async def stand_up(
        table_id: str, body: CreateTableRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        command = StandUp(command_id=body.command_id, table_id=table_id)
        return await seating_answer(partial(tables.stand, actor_of(request), command), presence, table_id, response)

    @router.get(TABLES_PATH + "/{table_id}", responses={404: {"description": "No table has this id."}})
    async def read_table(table_id: str, request: Request, response: Response) -> TableAnswer:
        response.headers["Cache-Control"] = "no-store"
        # Presence belongs to the event loop's thread; only the store read leaves it.
        view = await run_in_threadpool(tables.view, actor_of(request), table_id, presence.connected(table_id))
        if view is None:
            raise HTTPException(status_code=404, detail="table not found")
        return answer_of(view)

    # Any id gets the page: it asks the API and shows "Tisch nicht gefunden" for an id that is no table.
    @router.api_route(TABLE_PAGE_PREFIX + "{table_id}", methods=READ_METHODS)
    def table_page(table_id: str) -> Response:  # noqa: ARG001 - the page reads the id from its own address
        response = built_page_response(page_build.shell)
        response.headers["Cache-Control"] = "no-cache"
        return response

    return router
