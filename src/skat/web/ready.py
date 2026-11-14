from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.ready import NewSeriesCommand, ReadyCommand
from skat.web.mcp import CONTINUE_AFTER_RESULT_MARK, START_NEW_SERIES_MARK
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
    from collections.abc import Callable

    from skat.table.service import TableService
    from skat.table.views import CommandResult
    from skat.web.presence import Presence

# „Weiter“ after a result: `TABLES_PATH/{table_id}` plus this.
TABLE_READY_SUFFIX: Final = "/ready"
# „Neue Serie“ after a series' end: `TABLES_PATH/{table_id}` plus this.
TABLE_NEW_SERIES_SUFFIX: Final = "/new-series"


class SeriesRequest(CommandRequest):
    """A client names the series it saw by its number, `series.number` in the table's answer: its chair comes from the
    session.
    """

    series: Annotated[int, Field(strict=True, ge=1)]


class ReadyRequest(SeriesRequest):
    """„Weiter“ names the result it saw too, by its number in the table's list."""

    ordinal: Annotated[int, Field(strict=True, ge=1)]


async def _answer_and_deal(
    command: Callable[[frozenset[str]], CommandResult | None], presence: Presence, table_id: str, response: Response
) -> Response | TableAnswer:
    answer = await command_answer(command, presence, table_id, response)
    # A replay asks again, so a deal lost after the first commit follows the retry.
    if isinstance(answer, TableAnswer):
        await presence.deal_now(table_id)
    return answer


def create_ready_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_READY_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=CONTINUE_AFTER_RESULT_MARK,
    )
    async def tap_weiter(
        table_id: TableIdInPath, body: ReadyRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Weiter“ after a result of a Skat table: the caller's chair is ready for the next hand of the series.

        Use it when read_table or your table's view shows a `result`, the series is not over (`series` is null or
        `series.over` is false), and the caller's own chair (`is_mine`) has `ready: false`. The `ordinal` is
        `result.ordinal`, the `series` is `series.number` (1 when `series` is null).
        Refused: not seated, no result, a stale series, a stale ordinal, the series is over. Once read_table or
        your table's view shows `series.over: true` no next hand follows; call start_new_series for the next series,
        also after a passed-in last game (`passed_in`). After any other passed-in hand the next hand follows once all
        three are there. The result still stands in read_table; the next hand appears in a later read, once all three
        chairs are ready and the series is not over.
        """
        command = ReadyCommand(command_id=body.command_id, table_id=table_id, ordinal=body.ordinal, series=body.series)
        return await _answer_and_deal(
            partial(tables.mark_ready, actor_of(request), command), presence, table_id, response
        )

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_NEW_SERIES_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=START_NEW_SERIES_MARK,
    )
    async def start_new_series(
        table_id: TableIdInPath, body: SeriesRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Neue Serie“ after a Skat table's series has ended: the caller's chair is ready for the next series.

        Use it when read_table or your table's view shows `series.over: true` and the caller's own chair (`is_mine`) has
        `ready: false`; the `series` is `series.number`, and a tap naming another series than
        the table's changes nothing and is refused. Once all three seated members have tapped and
        are connected, the third tap makes the table's list read empty (the finished games stay stored), the count
        starts again and the next series' first hand is dealt. Refused: not seated, no series, a stale series, the
        series is not over. After the third tap read_table still shows the series' end; the next series' first hand
        appears in a later read.
        """
        command = NewSeriesCommand(command_id=body.command_id, table_id=table_id, series=body.series)
        return await _answer_and_deal(
            partial(tables.start_new_series, actor_of(request), command), presence, table_id, response
        )

    return router
