from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from skat.engine.kontra import Word  # noqa: TC001 - pydantic reads the field type at runtime
from skat.engine.value import Level  # noqa: TC001 - pydantic reads the field type at runtime
from skat.web.mcp import READ_SERIES_LIST_MARK
from skat.web.tables import (
    ANNOUNCEMENT_TOKENS,
    GAME_TOKENS,
    TABLES_PATH,
    AnnouncementToken,
    GameToken,
)

if TYPE_CHECKING:
    from skat.table.game_list import SeriesEntryView
    from skat.table.service import TableService

# The table's list of finished games: `TABLES_PATH/{table_id}` plus this.
TABLE_LIST_SUFFIX: Final = "/list"


class SeriesEntryAnswer(BaseModel):
    number: int
    declarer_name: str | None
    game: GameToken
    hand: bool
    ouvert: bool
    announcement: AnnouncementToken
    levels: list[Level]
    settled_value: int
    score: int
    kontra_word: Word | None


class SeriesListAnswer(BaseModel):
    entries: list[SeriesEntryAnswer]


def _entry_answer_of(entry: SeriesEntryView) -> SeriesEntryAnswer:
    declaration = entry.declaration
    return SeriesEntryAnswer(
        number=entry.number,
        declarer_name=entry.declarer_name,
        game=GAME_TOKENS[declaration.kind],
        hand=declaration.hand,
        ouvert=declaration.ouvert,
        announcement=ANNOUNCEMENT_TOKENS[declaration.announcement],
        levels=list(entry.levels),
        settled_value=entry.settled_value,
        score=entry.score,
        kontra_word=entry.kontra_word,
    )


def create_game_list_router(tables: TableService) -> APIRouter:
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_LIST_SUFFIX,
        responses={404: {"description": "No table has this id."}},
        openapi_extra=READ_SERIES_LIST_MARK,
    )
    async def read_series_list(table_id: str, response: Response) -> SeriesListAnswer:
        """Read the list of finished games of one Skat table, the same for every caller.

        One entry per game played so far, in the order played: its `number`, the `declarer_name` stored with the
        game (null for a game stored before names were kept), the game, its `levels`, its `settled_value` and the
        declarer's `score`, which is negative for a lost game, and the `kontra_word`, the last word said or null. A
        game with a word has its list score doubled once per word said. A hand everyone passed in leaves no entry. A 404
        means no table has this id; a table that has ended answers an empty list.
        """
        response.headers["Cache-Control"] = "no-store"
        entries = await run_in_threadpool(tables.series_list, table_id)
        if entries is None:
            raise HTTPException(status_code=404, detail="table not found")
        return SeriesListAnswer(entries=[_entry_answer_of(entry) for entry in entries])

    return router
