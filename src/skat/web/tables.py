from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from webauth.middleware import admitted_user

from skat.table.records import Actor, CreateTable
from skat.table.service import CommandIdReusedError
from skat.web.routes import READ_METHODS, built_page_response

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.table.views import TableView
    from skat.web.page_build import PageBuild

TABLES_PATH: Final = "/api/tables"
TABLE_PAGE_PREFIX: Final = "/t/"
# The browser's `crypto.randomUUID()` writes 36 characters of this alphabet.
COMMAND_ID_PATTERN: Final = r"^[A-Za-z0-9_-]{8,64}$"


class CreateTableRequest(BaseModel):
    """A client names only its retry key: the opener's account and chair come from the session."""

    model_config = ConfigDict(extra="forbid")

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]


class ChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    is_mine: bool


class TableAnswer(BaseModel):
    id: str
    version: int
    chairs: list[ChairAnswer]


def _answer(view: TableView) -> TableAnswer:
    return TableAnswer(
        id=view.id,
        version=view.version,
        chairs=[ChairAnswer(seat=c.seat, occupant_name=c.occupant_name, is_mine=c.is_mine) for c in view.chairs],
    )


def _actor(request: Request) -> Actor:
    user = admitted_user(request)
    # The gate refuses a request without a session before the route runs, so a missing user is a wiring fault.
    if user is None:  # pragma: no cover
        message = "A table route ran without an admitted user."
        raise RuntimeError(message)
    return Actor(account_id=user.id, display_name=user.username)


def create_tables_router(tables: TableService, page_build: PageBuild) -> APIRouter:
    router = APIRouter()

    @router.post(TABLES_PATH, responses={409: {"description": "The command id came back with another request."}})
    def create_table(body: CreateTableRequest, request: Request, response: Response) -> TableAnswer:
        # The answer names people, so no cache may keep it past the gate.
        response.headers["Cache-Control"] = "no-store"
        try:
            return _answer(tables.create(_actor(request), CreateTable(command_id=body.command_id)))
        except CommandIdReusedError:
            raise HTTPException(status_code=409, detail="command id reused with another request") from None

    @router.get(TABLES_PATH + "/{table_id}", responses={404: {"description": "No table has this id."}})
    def read_table(table_id: str, request: Request, response: Response) -> TableAnswer:
        response.headers["Cache-Control"] = "no-store"
        view = tables.view(_actor(request), table_id)
        if view is None:
            raise HTTPException(status_code=404, detail="table not found")
        return _answer(view)

    # Any id gets the page: it asks the API and shows "Tisch nicht gefunden" for an id that is no table.
    @router.api_route(TABLE_PAGE_PREFIX + "{table_id}", methods=READ_METHODS)
    def table_page(table_id: str) -> Response:  # noqa: ARG001 - the page reads the id from its own address
        response = built_page_response(page_build.shell)
        response.headers["Cache-Control"] = "no-cache"
        return response

    return router
