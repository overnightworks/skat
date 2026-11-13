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


class ReadyRequest(CommandRequest):
    """A client names only the result it saw, by its number in the table's list: its chair comes from the session."""

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
        table_id: str, body: ReadyRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Weiter“ after a result of a Skat table: the caller's chair is ready for the next hand of the series.

        Use it when read_table or your table's view shows a `result`, the series is not over (`series` is null or
        `series.over` is false), and the caller's own chair (`is_mine`) has `ready: false`. The `ordinal` is
        `result.ordinal` and the table id comes from the same read. The command id names this step: the same id with the
        same ordinal is a retry that changes nothing twice. A refusal (not seated, no result, a stale ordinal, the
        series is over) comes back as a failed result with its reason and spends the command id: the next attempt takes
        a new command id. Once read_table or your table's view shows `series.over: true` no next hand follows; call
        start_new_series for the next series, also after a passed-in last game (`passed_in`). After any other passed-in
        hand the next hand follows once all three are there. The answer still shows the result; the next hand appears in
        a later read_table, once all three chairs are ready and the series is not over.
        """
        command = ReadyCommand(command_id=body.command_id, table_id=table_id, ordinal=body.ordinal)
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
        table_id: str, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Neue Serie“ after a Skat table's series has ended: the caller's chair is ready for the next series.

        Use it when read_table or your table's view shows `series.over: true` and the caller's own chair (`is_mine`) has
        `ready: false`; the table id comes from the same read. Once all three seated members have tapped and are
        connected, the third tap makes the table's list read empty (the finished games stay stored), the count starts
        again and the next series' first hand is dealt. The command id names this step: the same id is a retry that
        changes nothing twice. A refusal (not seated, no series, the series is not over) comes back as a failed
        result with its reason and spends the command id: the next attempt takes a new command id. The answer to the
        third tap still shows the series' end; the next series' first hand appears in the next read.
        """
        command = NewSeriesCommand(command_id=body.command_id, table_id=table_id)
        return await _answer_and_deal(
            partial(tables.start_new_series, actor_of(request), command), presence, table_id, response
        )

    return router
