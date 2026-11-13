from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.records import CloseTable
from skat.web.mcp import Exclusion, excluded
from skat.web.tables import COMMAND_RESPONSES, TABLES_PATH, CommandRequest, TableAnswer, actor_of, command_answer

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# The command that closes a table: `TABLES_PATH/{table_id}` plus this.
TABLE_CLOSE_SUFFIX: Final = "/close"


def create_closing_router(tables: TableService, presence: Presence) -> APIRouter:
    """The route on which the opener closes a table for everyone."""
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_CLOSE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.FINAL_DELETION),
    )
    async def close_table(
        table_id: str, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Close a Skat table for everyone. Only the account that opened it may. The table ends at once, with a
        running hand deleted and the finished games kept, and the answer is the ended table. The command id names this
        step: the same id again is a retry that answers the ended table. A refusal (`not-allowed`: the caller did not
        open the table) leaves the table as it was and spends nothing.
        """
        command = CloseTable(command_id=body.command_id, table_id=table_id)
        actor = actor_of(request)
        answer = await command_answer(lambda _connected: tables.close(actor, command), presence, table_id, response)
        if isinstance(answer, TableAnswer):
            presence.table_ended(table_id)
        return answer

    return router
