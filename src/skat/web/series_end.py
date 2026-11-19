from functools import partial
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.series_end import END_ANSWER_SECONDS, SeriesEndCommand
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
        """Say yes to ending a Skat table's series early, between games, as every seated member has the same say.

        With no proposal standing this proposes the end, and you are the proposer; with one standing it adds your yes.
        The series ends only when every seat has said yes; then `series.over` turns true and `series.standings`
        appears, and no next hand follows. A seat that says no, or that stays silent for one minute after the proposal
        (`series.end_proposal.answer_by`), counts as no: the proposal ends, the series runs on and
        `series.end_refused_seats` names those seats until the next hand, which gives no new proposal before it. Use it
        from the caller's chair when read_table or your table's view shows a `series` that is not over and no `hand`;
        `series.end_proposal` names the seat that proposed and the seats that said yes. Refused: not seated, no series,
        the series is over, a hand runs, no game yet, a proposal was refused since the last hand.
        """
        command = SeriesEndCommand(command_id=body.command_id, table_id=table_id)
        answer = await command_answer(
            partial(tables.agree_to_end_series, actor_of(request), command), presence, table_id, response
        )
        # Another timer for the same proposal finds its minute not over yet, or the proposal gone.
        if isinstance(answer, TableAnswer) and answer.series is not None and answer.series.end_proposal is not None:
            presence.end_answer_watch.watch(table_id, END_ANSWER_SECONDS)
        return answer

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SERIES_END_REFUSE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=REFUSE_TO_END_SERIES_MARK,
    )
    async def refuse_to_end_series(
        table_id: TableIdInPath, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say no to the proposal to end a Skat table's series early: the proposal ends, the series plays on and
        `series.end_refused_seats` names your seat until the next hand.

        Every seat must say yes for the series to end, and a seat silent for one minute after the proposal counts as
        no, so saying nothing is a no too. Use it from the caller's chair when read_table or your table's view shows
        `series.end_proposal`, which names the seat that proposed. Refused: not seated, no proposal.
        """
        command = SeriesEndCommand(command_id=body.command_id, table_id=table_id)
        return await command_answer(
            partial(tables.refuse_to_end_series, actor_of(request), command), presence, table_id, response
        )

    return router
