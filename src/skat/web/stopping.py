from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.records import StopPlaying
from skat.web.mcp import STOP_PLAYING_MARK
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

# „Aufhören“ at a series' end: `TABLES_PATH/{table_id}` plus this.
TABLE_STOP_PLAYING_SUFFIX: Final = "/stop-playing"


def create_stopping_router(tables: TableService, presence: Presence) -> APIRouter:
    """The route on which a seated person ends the table at the series' end."""
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_STOP_PLAYING_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=STOP_PLAYING_MARK,
    )
    async def stop_playing(
        table_id: TableIdInPath, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Aufhören“ after a Skat table's series has ended: the table ends for everyone at once, every page returns
        to the lobby, and the table's link then shows the final standings and the games.

        This is the answer to „Neue Serie“ for a seat that does not want to play on; a seat that stays silent for one
        minute after the first „Neue Serie“ ends the table the same way (`series.new_series_answer_by`). Use it when
        read_table or your table's view shows `series.over: true`. The answer is the ended table (`ended.reason` is
        `closed` and `closed_by_name` is null). The command id names this step: the same id again is a retry that
        answers the ended table.
        Refused: not seated, no series, the series is not over; a refusal leaves the table as it was and spends
        nothing.
        """
        command = StopPlaying(command_id=body.command_id, table_id=table_id)
        answer = await command_answer(
            lambda _connected: tables.stop_playing(actor_of(request), command), presence, table_id, response
        )
        if isinstance(answer, TableAnswer) and answer.ended is not None:
            presence.table_ended(table_id)
        return answer

    return router
