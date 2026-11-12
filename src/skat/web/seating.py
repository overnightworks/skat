from functools import partial
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from skat.table.records import SERIES_LENGTH_MAX, SERIES_LENGTH_MIN, SERIES_LENGTH_STEP, CreateTable, SitDown, StandUp
from skat.table.rules import CHAIRS_PER_TABLE
from skat.table.service import CommandIdReusedError
from skat.web.mcp import OPEN_TABLE_MARK, SIT_DOWN_MARK, STAND_UP_MARK
from skat.web.table_options import OptionsRequest, table_options_of
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
    CommandRequest,
    TableAnswer,
    actor_of,
    answer_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence


class CreateTableRequest(CommandRequest):
    """The opener names the series length and may set the rule options; without them the table plays the official
    rules.
    """

    series_length: Annotated[
        int, Field(strict=True, ge=SERIES_LENGTH_MIN, le=SERIES_LENGTH_MAX, multiple_of=SERIES_LENGTH_STEP)
    ]
    options: OptionsRequest | None = None


class SitDownRequest(CommandRequest):
    seat: Annotated[int, Field(strict=True, ge=1, le=CHAIRS_PER_TABLE)]


def _create_chairs_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SIT_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=SIT_DOWN_MARK,
    )
    async def sit_down(
        table_id: str, body: SitDownRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Take a free chair at a Skat table.

        The table id is the last part of the table's link /t/{id}, which a person gives the caller, or the id of a
        table the caller opened. `seat` is the chair's number, 1 to 3: a chair whose `occupant_name` is null in the
        answer of read_table. Whoever sits first has the chair. The sit that fills the third chair deals the first
        hand; while a game's result stands, sitting down counts as continuing. At a table whose running hand waits
        for a sitter (`hand.waiting_seat` is set in the answer), the sit takes that seat over as it stands: its cards,
        its role and its turn, and the hand moves again once no chair is open; a caller that held another chair of
        this hand cannot take it. The command id names this step: the
        same id with the same seat is a retry that changes nothing twice. A refusal (the chair is taken, and the
        answer names who holds it; the caller already sits at this table; `own-seat-only`: the caller left another
        chair of the running hand and may sit only in that one until the hand ends) comes back as a failed result with
        its reason, leaves the table as it was and spends the command id.
        """
        command = SitDown(command_id=body.command_id, table_id=table_id, seat=body.seat)
        answer = await command_answer(partial(tables.sit, actor_of(request), command), presence, table_id, response)
        # A sit while a result is pending marks the sitter ready, which may complete the marks.
        if isinstance(answer, TableAnswer):
            presence.chair_taken(table_id)
            if answer.result is not None:
                await presence.deal_now(table_id)
        return answer

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_STAND_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=STAND_UP_MARK,
    )
    async def stand_up(
        table_id: str, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Leave the caller's own chair at a Skat table.

        The chair keeps its number and becomes free, at any time. While a hand runs, the hand waits for a sitter
        (`hand.waiting_seat` is set in the answer) and nothing is scored; until that hand ends the caller may sit
        again only in the chair it left. The command id names this step: the same id again is a retry that changes
        nothing twice. A refusal (the caller holds no chair here) comes back as a failed result with its reason,
        leaves the table as it was and spends the command id.
        """
        command = StandUp(command_id=body.command_id, table_id=table_id)
        answer = await command_answer(partial(tables.stand, actor_of(request), command), presence, table_id, response)
        if isinstance(answer, TableAnswer):
            presence.chair_freed(table_id)
        return answer

    return router


def create_seating_router(tables: TableService, presence: Presence) -> APIRouter:
    """The routes that open a table and take or leave its chairs."""
    router = APIRouter()

    @router.post(
        TABLES_PATH,
        responses={409: {"description": "The command id came back with another request."}},
        openapi_extra=OPEN_TABLE_MARK,
    )
    async def create_table(body: CreateTableRequest, request: Request, response: Response) -> TableAnswer:
        """Open a new Skat table, with the caller in chair 1 as its opener.

        `series_length` is the number of games its series runs, within the bounds of the input schema. `options` may
        switch on the table's rule options, which stay fixed for its life; without them it plays the official rules. The
        answer is the table as read_table gives it. Its `id` makes the table's link /t/{id}, which the caller gives
        the people it wants to play with. The command id names this opening: the same id with the same request is a
        retry that opens no second table, and the same id with another request is refused.
        """
        # The answer names people, so no cache may keep it past the gate.
        response.headers["Cache-Control"] = "no-store"
        try:
            options = table_options_of(body.options)
            command = CreateTable(command_id=body.command_id, series_length=body.series_length, options=options)
            view = await run_in_threadpool(tables.create, actor_of(request), command)
        except CommandIdReusedError:
            raise HTTPException(status_code=409, detail="command id reused with another request") from None
        # Presence belongs to the event loop's thread, so the wait and the note start here and not on the worker.
        if view.ended is None:
            presence.chair_taken(view.id)
        return answer_of(view)

    router.include_router(_create_chairs_router(tables, presence))
    return router
