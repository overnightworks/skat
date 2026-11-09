from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.ready import ReadyCommand
from skat.web.mcp import CONTINUE_AFTER_RESULT_MARK
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
        TABLES_PATH + "/{table_id}" + TABLE_READY_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=CONTINUE_AFTER_RESULT_MARK,
    )
    async def tap_weiter(
        table_id: str, body: ReadyRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Weiter“ after a result of a Skat table: the caller's chair is ready for the next hand.

        Use it when read_table shows a `result` and the caller's own chair (`is_mine`) has `ready: false`. The
        `ordinal` is `result.ordinal` and the table id comes from the same read. The command id names this
        step: the same id with the same ordinal is a retry that changes nothing twice. A refusal (not seated, no
        result, a stale ordinal) comes back as a failed result with its reason and spends the command id: the next
        attempt takes a new command id. After a passed-in hand (`passed_in`) there is nothing to do: the next hand
        follows once all three are there. The answer still shows the result; the next hand appears in a later
        read_table, once all three chairs are ready.
        """
        command = ReadyCommand(command_id=body.command_id, table_id=table_id, ordinal=body.ordinal)
        answer = await command_answer(
            partial(tables.mark_ready, actor_of(request), command), presence, table_id, response
        )
        # A replay asks again, so a deal lost after the first commit follows the retry.
        if isinstance(answer, TableAnswer):
            await presence.deal_now(table_id)
        return answer

    return router
