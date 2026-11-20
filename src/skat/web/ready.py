from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.ready import NewSeriesCommand, NextSettingsCommand, ReadyCommand
from skat.table.series_end import END_ANSWER_SECONDS
from skat.web.mcp import CHANGE_NEXT_SERIES_SETTINGS_MARK, CONTINUE_AFTER_RESULT_MARK, START_NEW_SERIES_MARK
from skat.web.table_options import OptionsRequest, SeriesLengthRequest, table_options_of
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
# The next series' settings after a series' end: `TABLES_PATH/{table_id}` plus this.
TABLE_NEXT_SETTINGS_SUFFIX: Final = "/next-settings"


class SeriesRequest(CommandRequest):
    """A client names the series it saw by its number, `series.number` in the table's answer: its chair comes from the
    session.
    """

    series: Annotated[int, Field(strict=True, ge=1)]


class NewSeriesRequest(SeriesRequest):
    """„Neue Serie“ names the revision of the next series' settings it answers, `series.next_settings.revision`; left
    out, as a page of the release before sends it, it answers the settings the last series carried over, revision 0, so
    it is refused once a seat saved others.
    """

    settings: Annotated[int, Field(strict=True, ge=0)] = 0


class NextSettingsRequest(SeriesRequest):
    """The next series' length and rule options as the sheet that opens a table names them; left out, `options` are the
    official rules.
    """

    series_length: SeriesLengthRequest
    options: OptionsRequest | None = None

    def command_of(self, table_id: str) -> NextSettingsCommand:
        return NextSettingsCommand(
            command_id=self.command_id,
            table_id=table_id,
            series=self.series,
            length=self.series_length,
            options=table_options_of(self.options),
        )


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
        also after a passed-in last game (`passed_in`), or stop_playing to end the table. After any other passed-in hand
        the next hand follows once all three are there. The result still stands in read_table; the next hand appears
        in a later read, once all three chairs are ready and the series is not over.
        """
        command = ReadyCommand(command_id=body.command_id, table_id=table_id, ordinal=body.ordinal, series=body.series)
        return await _answer_and_deal(
            partial(tables.mark_ready, actor_of(request), command), presence, table_id, response
        )

    _add_start_new_series(router, tables, presence)
    _add_change_next_series_settings(router, tables, presence)
    return router


def _add_change_next_series_settings(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_NEXT_SETTINGS_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=CHANGE_NEXT_SERIES_SETTINGS_MARK,
    )
    async def change_next_series_settings(
        table_id: TableIdInPath, body: NextSettingsRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Change what the next series of a Skat table is played with, after its series has ended: the same length and
        rule options the sheet shows that opens a table, which a person opens with „Ändern“ under the standings.

        Use it when read_table or your table's view shows `series.over: true`; `series.next_settings` holds the
        `game_count` and `options` the next series is played with now, the last series' until someone saves, and a
        `revision` that counts the saves. The `series` is `series.number`; `series_length` is the number of games, a
        multiple of three from 3 to 99, and `options` are the table's rule options as open_table names them, the
        official rules when left out. A save replaces the settings, shows at once on every page, and takes back every
        seat's „Neue Serie“, yours too, since each was given on the settings before: tap again with start_new_series on
        the new `series.next_settings.revision`. The minute that follows the first „Neue Serie“ starts again with
        the next one. Refused: not seated, no series, a stale series, the series is not over, the minute is over
        (`answer-time-over`); invalid settings are refused as open_table refuses them.
        """
        return await command_answer(
            partial(tables.change_next_settings, actor_of(request), body.command_of(table_id)),
            presence,
            table_id,
            response,
        )


def _add_start_new_series(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_NEW_SERIES_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=START_NEW_SERIES_MARK,
    )
    async def start_new_series(
        table_id: TableIdInPath, body: NewSeriesRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say „Neue Serie“ after a Skat table's series has ended: the caller's chair is ready for the next series.

        Use it when read_table or your table's view shows `series.over: true` and the caller's own chair (`is_mine`) has
        `ready: false`; the `series` is `series.number`, the `settings` is `series.next_settings.revision` (0 when left
        out), and a tap naming another series than the table's, or settings the table no longer holds, changes nothing
        and is refused.
        Once all three seated members have tapped and are connected, the third tap makes the table's list read empty
        (the finished games stay stored), the count starts again and the next series' first hand is dealt. The first
        tap starts a minute (`series.new_series_answer_by`): a seated member who has not tapped by then counts as no,
        and the table ends and everyone returns to the lobby, so tap in time or call stop_playing. Refused: not seated,
        no series, a stale series, the series is not over, stale settings (`stale-settings`: read the table again and
        tap on the settings it shows), the minute is over (`answer-time-over`). After the third tap read_table still
        shows the series' end; the next series' first hand appears in a later read.
        """
        command = NewSeriesCommand(
            command_id=body.command_id, table_id=table_id, series=body.series, settings=body.settings
        )
        answer = await _answer_and_deal(
            partial(tables.start_new_series, actor_of(request), command), presence, table_id, response
        )
        # Another timer for the same minute finds it not over yet, or the series dealt.
        if isinstance(answer, TableAnswer) and answer.series is not None and answer.series.new_series_answer_by:
            presence.end_answer_watch.watch(table_id, END_ANSWER_SECONDS)
        return answer
