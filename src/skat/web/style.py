from functools import partial
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.records import TableStyle  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.style import StyleCommand
from skat.web.mcp import Exclusion, excluded
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLES_PATH,
    CommandRequest,
    TableAnswer,
    TableIdInPath,
    actor_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# The table's style: `TABLES_PATH/{table_id}` plus this.
TABLE_STYLE_SUFFIX: Final = "/style"


class StyleRequest(CommandRequest):
    """A client names the style the whole table gets: its chair comes from the session."""

    style: TableStyle


def create_style_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_STYLE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.TABLE_LOOK),
    )
    async def choose_style(
        table_id: TableIdInPath, body: StyleRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Give the table a style: it changes for everyone at the table, watchers included.

        Refused: not seated. The style the table already has changes nothing and is no error.
        """
        command = StyleCommand(command_id=body.command_id, table_id=table_id, style=body.style)
        return await command_answer(
            partial(tables.change_style, actor_of(request), command), presence, table_id, response
        )

    return router
