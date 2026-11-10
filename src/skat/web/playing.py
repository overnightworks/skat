from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.playing import GiveUpCommand, PlayCardCommand, ThrowDownCommand
from skat.web.mcp import GIVE_UP_GAME_MARK, PLAY_CARD_MARK, THROW_DOWN_CARDS_MARK
from skat.web.tables import (
    COMMAND_ID_PATTERN,
    COMMAND_RESPONSES,
    TABLES_PATH,
    CardChoice,
    CommandRequest,
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
# The declarer's give-up on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_SUFFIX: Final = "/give-up"
# A side's throw-down on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_THROW_DOWN_SUFFIX: Final = "/throw-down"


class PlayCardRequest(CardChoice):
    """A client names only the card and the version it saw: its seat and position come from the session."""

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]
    version: Annotated[int, Field(strict=True)]


class GiveUpRequest(CommandRequest):
    """A client names only the version it saw: it cannot send consent, and its seat comes from the session."""

    version: Annotated[int, Field(strict=True)]


class ThrowDownRequest(CommandRequest):
    """A client names only the version it saw: its seat, and so its side, come from the session."""

    version: Annotated[int, Field(strict=True)]


def create_playing_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    _add_play_card(router, tables, presence)
    _add_give_up(router, tables, presence)
    _add_throw_down(router, tables, presence)
    return router


def _add_play_card(router: APIRouter, tables: TableService, presence: Presence) -> None:
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
        command id names this move: the same id with the same card and the same version is a retry that changes
        nothing twice. A refusal (a stale version, a card that is not legal, not the caller's turn) comes back as a
        failed result with its reason, leaves the table as it was and spends the command id: the next attempt takes
        a new command id.
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


def _add_give_up(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_GIVE_UP_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=GIVE_UP_GAME_MARK,
    )
    async def give_up_game(
        table_id: str, body: GiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Give up the game the caller declared and lose it at once, valued as declared; this cannot be undone.

        Use it when `hand.declaring.declarer_seat` in the answer of read_table is the chair marked `is_mine`, once
        `hand.playing` is set and while the caller's chair holds nine or more cards, on anyone's turn. The table id and
        the version come from that answer. The command id names this step: the same id with the same version is a
        retry that changes nothing twice. A refusal (a stale version, not the declarer, fewer than nine cards) comes
        back as a failed result with its reason, leaves the table as it was and spends the command id: the next
        attempt takes a new command id.
        """
        command = GiveUpCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(
                tables.give_up,
                actor_of(request),
                command,
                on_hand_ended=partial(presence.restart_leaves, table_id),
            ),
            presence,
            table_id,
            response,
        )


def _add_throw_down(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_THROW_DOWN_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=THROW_DOWN_CARDS_MARK,
    )
    async def throw_down_cards(
        table_id: str, body: ThrowDownRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Throw the caller's cards down and end the game at once for the caller's side; this cannot be undone.

        The caller's side keeps the tricks it has completed; every card in no completed trick, the trick in progress
        included, counts for the other side, and the skat for the declarer. No card is shown. Use it from the
        caller's chair once `hand.playing` is set in the answer of read_table, on anyone's turn, as declarer or as
        opponent. The table id and the version come from that answer. The command id names this step: the same id
        with the same version is a retry that changes nothing twice. A refusal (a stale version, no game in play,
        not seated) comes back as a failed result with its reason, leaves the table as it was and spends the
        command id: the next attempt takes a new command id.
        """
        command = ThrowDownCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(
                tables.throw_down,
                actor_of(request),
                command,
                on_hand_ended=partial(presence.restart_leaves, table_id),
            ),
            presence,
            table_id,
            response,
        )
