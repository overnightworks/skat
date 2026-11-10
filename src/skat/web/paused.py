from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from skat.web.mcp import READ_PAUSED_TABLES_MARK
from skat.web.tables import actor_of

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.table.views import PausedEntryView

PAUSED_TABLES_PATH: Final = "/api/paused-tables"


class PausedChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    is_mine: bool
    total: int | None


class PausedTableAnswer(BaseModel):
    id: str
    chairs: list[PausedChairAnswer]
    game_number: int | None
    game_count: int | None
    turn_seat: int | None
    result_waits: bool


class PausedTablesAnswer(BaseModel):
    tables: list[PausedTableAnswer]


def _table_answer_of(entry: PausedEntryView) -> PausedTableAnswer:
    return PausedTableAnswer(
        id=entry.id,
        chairs=[
            PausedChairAnswer(
                seat=chair.seat, occupant_name=chair.occupant_name, is_mine=chair.is_mine, total=chair.total
            )
            for chair in entry.chairs
        ],
        game_number=entry.game_number,
        game_count=entry.game_count,
        turn_seat=entry.turn_seat,
        result_waits=entry.result_waits,
    )


def create_paused_router(tables: TableService) -> APIRouter:
    router = APIRouter()

    @router.get(PAUSED_TABLES_PATH, openapi_extra=READ_PAUSED_TABLES_MARK)
    async def read_paused_tables(request: Request, response: Response) -> PausedTablesAnswer:
        """Read the Skat tables on which a hand was dealt and where the caller holds a chair: for each its id for
        read_table, the chairs in order with their names, the caller's own and the running totals, the game number
        and series length (null for a table without a series), and the seat whose move the hand waits for or whether
        a result waits. No card is in it. An empty list means the caller holds no chair at a dealt table.
        """
        response.headers["Cache-Control"] = "no-store"
        entries = await run_in_threadpool(tables.paused_tables, actor_of(request))
        return PausedTablesAnswer(tables=[_table_answer_of(entry) for entry in entries])

    return router
