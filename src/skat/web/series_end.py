from functools import partial
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.series_end import SeriesEndCommand
from skat.web.mcp import AGREE_TO_END_SERIES_MARK, REFUSE_TO_END_SERIES_MARK
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

# A yes to ending the series early: `TABLES_PATH/{table_id}` plus this.
TABLE_SERIES_END_AGREE_SUFFIX: Final = "/series-end/agree"
# A no to ending the series early: `TABLES_PATH/{table_id}` plus this.
TABLE_SERIES_END_REFUSE_SUFFIX: Final = "/series-end/refuse"


def create_series_end_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SERIES_END_AGREE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AGREE_TO_END_SERIES_MARK,
    )
    async def agree_to_end_series(
        table_id: TableIdInPath, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say yes to ending a Skat table's series early, between games.

        With no proposal standing this proposes the end; with one standing it accepts it. Once the other two seated
        members have both said yes, the series ends at once with the standings so far (`series.over` turns true and
        `series.standings` appears), and no next hand follows. Use it from the caller's chair when read_table or your
        table's view shows a `series` that is not over and no `hand`; `series.end_proposal` names the seat that proposed
        and the seat that accepted. Refused: not seated, no series, the series is over, a hand runs, no game yet.
        """
        command = SeriesEndCommand(command_id=body.command_id, table_id=table_id)
        return await command_answer(
            partial(tables.agree_to_end_series, actor_of(request), command), presence, table_id, response
        )

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SERIES_END_REFUSE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=REFUSE_TO_END_SERIES_MARK,
    )
    async def refuse_to_end_series(
        table_id: TableIdInPath, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say no to the proposal to end a Skat table's series early: the proposal goes and the series plays on.

        Use it from the caller's chair when read_table or your table's view shows `series.end_proposal`. Refused: not
        seated, no proposal.
        """
        command = SeriesEndCommand(command_id=body.command_id, table_id=table_id)
        return await command_answer(
            partial(tables.refuse_to_end_series, actor_of(request), command), presence, table_id, response
        )

    return router
