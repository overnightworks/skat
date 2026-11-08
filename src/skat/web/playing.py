from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.playing import PlayCardCommand
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLES_PATH,
    CardChoice,
    CreateTableRequest,
    TableAnswer,
    actor_of,
    card_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A card played on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_CARD_SUFFIX: Final = "/card"


class PlayCardRequest(CreateTableRequest, CardChoice):
    """A client names only the card and the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]


def create_playing_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_CARD_SUFFIX, response_model=TableAnswer, responses=COMMAND_RESPONSES
    )
    async def play_card(
        table_id: str, body: PlayCardRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        command = PlayCardCommand(
            command_id=body.command_id, table_id=table_id, version=body.version, card=card_of(body)
        )
        return await command_answer(partial(tables.play_card, actor_of(request), command), presence, table_id, response)

    return router
