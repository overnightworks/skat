from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.ready import ReadyCommand
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLES_PATH,
    CreateTableRequest,
    TableAnswer,
    actor_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# „Weiter“ after a result: `TABLES_PATH/{table_id}` plus this.
TABLE_READY_SUFFIX: Final = "/ready"


class ReadyRequest(CreateTableRequest):
    """A client names only the result it saw, by its number in the table's list: its chair comes from the session."""

    ordinal: Annotated[int, Field(strict=True, ge=1)]


def create_ready_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_READY_SUFFIX, response_model=TableAnswer, responses=COMMAND_RESPONSES
    )
    async def tap_weiter(
        table_id: str, body: ReadyRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        command = ReadyCommand(command_id=body.command_id, table_id=table_id, ordinal=body.ordinal)
        answer = await command_answer(
            lambda connected: tables.mark_ready(actor_of(request), command, connected), presence, table_id, response
        )
        # A replay asks again, so a deal lost after the first commit follows the retry.
        if isinstance(answer, TableAnswer):
            await presence.deal_now(table_id)
        return answer

    return router
