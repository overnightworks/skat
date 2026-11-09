from enum import StrEnum
from functools import partial
from typing import TYPE_CHECKING, Annotated, Final, Literal

from fastapi import APIRouter, Body, Request, Response
from pydantic import Field

from skat.engine.declaration import SKAT_SIZE, Declare, PutBack, TakeSkat
from skat.table.declaring import DeclaringCommand
from skat.web.mcp import Exclusion, excluded
from skat.web.tables import (
    ANNOUNCEMENT_TOKENS,
    COMMAND_RESPONSES,
    GAME_TOKENS,
    TABLES_PATH,
    AnnouncementToken,
    CardChoice,
    CommandRequest,
    GameToken,
    TableAnswer,
    actor_of,
    card_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.engine.declaration import DeclaringStep
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A take, put-back or declaration on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_DECLARATION_SUFFIX: Final = "/declaration"


class DeclaringAction(StrEnum):
    TAKE = "take"
    PUT_BACK = "put_back"
    DECLARE = "declare"


_GAME_KINDS: Final = {token: kind for kind, token in GAME_TOKENS.items()}
_ANNOUNCEMENTS: Final = {token: announcement for announcement, token in ANNOUNCEMENT_TOKENS.items()}


class _DeclaringRequest(CommandRequest):
    """A client names only the step and the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]


class TakeRequest(_DeclaringRequest):
    action: Literal[DeclaringAction.TAKE]


class PutBackRequest(_DeclaringRequest):
    action: Literal[DeclaringAction.PUT_BACK]
    cards: Annotated[list[CardChoice], Field(min_length=SKAT_SIZE, max_length=SKAT_SIZE)]


class DeclareRequest(_DeclaringRequest):
    """`hand=true` is how a Hand game is said: the take the page held back is no server step."""

    action: Literal[DeclaringAction.DECLARE]
    game: GameToken
    hand: Annotated[bool, Field(strict=True)]
    ouvert: Annotated[bool, Field(strict=True)]
    announcement: AnnouncementToken


type DeclaringRequest = TakeRequest | PutBackRequest | DeclareRequest


def _step_of(body: DeclaringRequest) -> DeclaringStep:
    if isinstance(body, TakeRequest):
        return TakeSkat()
    if isinstance(body, PutBackRequest):
        return PutBack(tuple(card_of(card) for card in body.cards))
    return Declare(
        _GAME_KINDS[body.game], hand=body.hand, ouvert=body.ouvert, announcement=_ANNOUNCEMENTS[body.announcement]
    )


def create_declaring_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_DECLARATION_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.UNION_BODY),
    )
    async def take_declaring_step(
        table_id: str,
        body: Annotated[DeclaringRequest, Body(discriminator="action")],
        request: Request,
        response: Response,
    ) -> Response | TableAnswer:
        command = DeclaringCommand(
            command_id=body.command_id, table_id=table_id, version=body.version, step=_step_of(body)
        )
        return await command_answer(
            partial(tables.take_declaring_step, actor_of(request), command), presence, table_id, response
        )

    return router
