from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.playing import PlayCardCommand
from skat.web.mcp import PLAY_CARD_MARK
from skat.web.tables import (
    COMMAND_ID_PATTERN,
    COMMAND_RESPONSES,
    TABLES_PATH,
    CardChoice,
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


class PlayCardRequest(CardChoice):
    """A client names only the card and the version it saw: its seat and position come from the session."""

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]
    version: Annotated[int, Field(strict=True)]


def create_playing_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_CARD_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=PLAY_CARD_MARK,
    )
    async def play_card(
        table_id: str, body: PlayCardRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Play one card from the caller's own hand on its turn at a Skat table.

        The table id and the version come from the answer of read_table, and the card from its legal cards. The
        command id names this move: the same id with the same card is a retry that changes nothing twice. A refusal
        (a stale version, a card that is not legal, not the caller's turn) comes back as a failed result with its
        reason and changes nothing.
        """
        command = PlayCardCommand(
            command_id=body.command_id, table_id=table_id, version=body.version, card=card_of(body)
        )
        return await command_answer(
            partial(
                tables.play_card,
                actor_of(request),
                command,
                on_hand_ended=partial(presence.restart_leaves, table_id),
            ),
            presence,
            table_id,
            response,
        )

    return router
