from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.engine.declaration import SKAT_SIZE, Declare, PutBack, TakeSkat
from skat.table.declaring import DeclaringCommand
from skat.web.mcp import DECLARE_GAME_MARK, PUT_BACK_CARDS_MARK, TAKE_SKAT_MARK
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

# A take, put-back or declaration on a table: `TABLES_PATH/{table_id}` plus the step's suffix.
TABLE_DECLARING_TAKE_SUFFIX: Final = "/declaring/take"
TABLE_DECLARING_PUT_BACK_SUFFIX: Final = "/declaring/put-back"
TABLE_DECLARING_DECLARE_SUFFIX: Final = "/declaring/declare"

_GAME_KINDS: Final = {token: kind for kind, token in GAME_TOKENS.items()}
_ANNOUNCEMENTS: Final = {token: announcement for announcement, token in ANNOUNCEMENT_TOKENS.items()}


class _DeclaringRequest(CommandRequest):
    """A client names only the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]


class PutBackRequest(_DeclaringRequest):
    cards: Annotated[list[CardChoice], Field(min_length=SKAT_SIZE, max_length=SKAT_SIZE)]


class DeclareRequest(_DeclaringRequest):
    """`hand=true` is how a Hand game is said: the take the page held back is no server step."""

    game: GameToken
    hand: Annotated[bool, Field(strict=True)]
    ouvert: Annotated[bool, Field(strict=True)]
    announcement: AnnouncementToken


type StepTaker = Callable[[str, _DeclaringRequest, Request, Response, DeclaringStep], Awaitable[Response | TableAnswer]]


def _step_taker(tables: TableService, presence: Presence) -> StepTaker:
    async def take_step(
        table_id: str, body: _DeclaringRequest, request: Request, response: Response, step: DeclaringStep
    ) -> Response | TableAnswer:
        command = DeclaringCommand(command_id=body.command_id, table_id=table_id, version=body.version, step=step)
        return await command_answer(
            partial(tables.take_declaring_step, actor_of(request), command), presence, table_id, response
        )

    return take_step


def _add_take(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_DECLARING_TAKE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=TAKE_SKAT_MARK,
    )
    async def take(
        table_id: str, body: _DeclaringRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Take the two skat cards into the hand of the declarer of a Skat table, who then holds twelve cards.

        Use it as the declarer, the winner of the auction, when `hand.declaring.stage` in the answer of read_table or
        the state of your table's view is "choosing" and `hand.declaring.declarer_seat` is the seat of the caller's own
        chair. Not taking the skat is how a Hand game is said, through declare_game. The table id and the version come
        from that answer. Then read_table holds all twelve cards in `hand.own_cards`; next is put_back_cards. The
        command id names this step: the same id with the same version is a retry that changes nothing twice. A refusal
        (for example stale-version, already-declared, not-declarer, out-of-order) comes back as a failed result with
        its reason, leaves the table as it was and spends the command id: the next attempt takes a new command id.
        """
        return await take_step(table_id, body, request, response, TakeSkat())


def _add_put_back(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_DECLARING_PUT_BACK_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=PUT_BACK_CARDS_MARK,
    )
    async def put_back(
        table_id: str, body: PutBackRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Put two cards back as the skat, any two of the twelve, from the hand of the declarer of a Skat table.

        Use it as the declarer when `hand.declaring.stage` in the answer of read_table or the state of your table's view
        is "discarding" and `hand.declaring.declarer_seat` is the seat of the caller's own chair. The table id and the
        version come from that answer. The two cards count for the declarer and vanish from every answer; next is
        declare_game with `hand` false. The command id names this step: the same id with the same cards and the same
        version is a retry that changes nothing twice. A refusal (for example stale-version, already-declared,
        not-declarer, out-of-order, not-two-of-the-twelve) comes back as a failed result with its reason, leaves the
        table as it was and spends the command id: the next attempt takes a new command id.
        """
        return await take_step(table_id, body, request, response, PutBack(tuple(card_of(card) for card in body.cards)))


def _add_declare(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_DECLARING_DECLARE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=DECLARE_GAME_MARK,
    )
    async def declare(
        table_id: str, body: DeclareRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Declare the game the declarer of a Skat table plays, and with it start the play of the hand.

        Use it as the declarer when `hand.declaring.stage` in the answer of read_table or the state of your table's view
        is "picked", with `hand` false, `announcement` "none" and `ouvert` only for a Null game, or is "choosing", with
        `hand` true, to play Hand without the skat: `announcement` "schneider" or "schwarz" then only for a suit or
        Grand game, and `ouvert` for Null, or for a suit or Grand game, which counts as announced Schwarz. The table id
        and the version come from that answer. The bid is `hand.auction.declared.value`; a game worth less is accepted
        and lost as overbid. Next the forehand leads with play_card. The command id names this step: the same id with
        the same fields and the same version is a retry that changes nothing twice. A refusal (for example
        stale-version, already-declared, not-declarer, out-of-order, level-not-allowed-after-pick-up,
        announcement-in-null) comes back as a failed result with its reason, leaves the table as it was and spends the
        command id: the next attempt takes a new command id.
        """
        step = Declare(
            _GAME_KINDS[body.game], hand=body.hand, ouvert=body.ouvert, announcement=_ANNOUNCEMENTS[body.announcement]
        )
        return await take_step(table_id, body, request, response, step)


def create_declaring_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    take_step = _step_taker(tables, presence)
    _add_take(router, take_step)
    _add_put_back(router, take_step)
    _add_declare(router, take_step)
    return router
