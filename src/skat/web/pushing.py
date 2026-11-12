from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.engine.declaration import SKAT_SIZE
from skat.engine.tricks import TRICKS_IN_A_GAME
from skat.table.pushing import PushingCommand, PushingKind
from skat.web.mcp import (
    RAMSCH_DECLARE_GRAND_HAND_MARK,
    RAMSCH_PUSH_SKAT_MARK,
    RAMSCH_PUT_BACK_CARDS_MARK,
    RAMSCH_TAKE_SKAT_MARK,
)
from skat.web.tables import (
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
    from skat.engine.cards import Card
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A seat's step of a Ramsch's stage on a table: `TABLES_PATH/{table_id}` plus the step's suffix.
TABLE_PUSHING_TAKE_SUFFIX: Final = "/pushing/take"
TABLE_PUSHING_PUT_BACK_SUFFIX: Final = "/pushing/put-back"
TABLE_PUSHING_PUSH_SUFFIX: Final = "/pushing/push"
TABLE_PUSHING_GRAND_HAND_SUFFIX: Final = "/pushing/grand-hand"


class _PushingRequest(CommandRequest):
    """A client names only the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]


class PutBackRequest(_PushingRequest):
    """The engine refuses a wrong count; the cap is the most a seat can hold after the take, so a body stays small."""

    cards: Annotated[list[CardChoice], Field(max_length=TRICKS_IN_A_GAME + SKAT_SIZE)]


type StepTaker = Callable[
    [str, _PushingRequest, Request, Response, PushingKind, tuple[Card, ...]], Awaitable[Response | TableAnswer]
]


def _step_taker(tables: TableService, presence: Presence) -> StepTaker:
    async def take_step(
        table_id: str,
        body: _PushingRequest,
        request: Request,
        response: Response,
        kind: PushingKind,
        cards: tuple[Card, ...],
    ) -> Response | TableAnswer:
        command = PushingCommand(
            command_id=body.command_id, table_id=table_id, version=body.version, kind=kind, cards=cards
        )
        return await command_answer(
            partial(tables.take_pushing_step, actor_of(request), command), presence, table_id, response
        )

    return take_step


def _add_take(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_PUSHING_TAKE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=RAMSCH_TAKE_SKAT_MARK,
    )
    async def take(
        table_id: str, body: _PushingRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Take the skat into your hand in the stage before a Ramsch, which then holds twelve cards.

        Use it when `hand.pushing` in the answer of read_table or the state of your table's view is set,
        `hand.pushing.turn_seat` is the seat of the caller's own chair and `hand.pushing.stage` is "choosing"; the
        other choice then is ramsch_push_skat. The table id and the version come from that answer. The answer holds all
        twelve cards in `hand.own_cards`; next is ramsch_put_back_cards. The command id names this step: the same id
        with the same version is a retry that changes nothing twice. A refusal (for example stale-version, wrong-phase,
        not-your-turn, out-of-order) comes back as a failed result with its reason, leaves the table as it was and
        spends the command id: the next attempt takes a new command id.
        """
        return await take_step(table_id, body, request, response, PushingKind.TAKE, ())


def _add_put_back(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_PUSHING_PUT_BACK_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=RAMSCH_PUT_BACK_CARDS_MARK,
    )
    async def put_back(
        table_id: str, body: PutBackRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Put two cards back as the skat after taking it in the stage before a Ramsch, any two of the twelve.

        Use it when `hand.pushing` in the answer of read_table or the state of your table's view is set,
        `hand.pushing.turn_seat` is the seat of the caller's own chair and `hand.pushing.stage` is "discarding". A
        table whose pushing rule is "jacks-stay" or "no-doubling" refuses a jack among the two (jack-put-back);
        "jacks-may-go" takes any two. The table id and the version come from that answer. The two cards leave your
        hand and the next seat meets them as the skat; a seat that follows takes or pushes it, and after the last
        seat's turn the Ramsch starts. The command id names this step: the same id with the same cards and the same
        version is a retry that changes nothing twice. A refusal (for example stale-version, wrong-phase,
        not-your-turn, out-of-order, not-two-of-the-twelve, jack-put-back) comes back as a failed result with its
        reason, leaves the table as it was and spends the command id: the next attempt takes a new command id.
        """
        cards = tuple(card_of(card) for card in body.cards)
        return await take_step(table_id, body, request, response, PushingKind.PUT_BACK, cards)


def _add_push(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_PUSHING_PUSH_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=RAMSCH_PUSH_SKAT_MARK,
    )
    async def push(
        table_id: str, body: _PushingRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Push the skat on unseen to the next seat in the stage before a Ramsch, without looking at it.

        Use it when `hand.pushing` in the answer of read_table or the state of your table's view is set,
        `hand.pushing.turn_seat` is the seat of the caller's own chair and `hand.pushing.stage` is "choosing"; the
        other choice then is ramsch_take_skat. The table id and the version come from that answer. Where the table's
        rule doubles, each push doubles the Ramsch's score (`hand.pushing.factor`); `hand.pushes` counts the pushes
        through the Ramsch's play. The command id names this step: the same id with the same version is a retry that
        changes nothing twice. A refusal (for example stale-version, wrong-phase, not-your-turn, out-of-order) comes
        back as a failed result with its reason, leaves the table as it was and spends the command id: the next
        attempt takes a new command id.
        """
        return await take_step(table_id, body, request, response, PushingKind.PUSH, ())


def _add_declare_grand_hand(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_PUSHING_GRAND_HAND_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=RAMSCH_DECLARE_GRAND_HAND_MARK,
    )
    async def declare_grand_hand(
        table_id: str, body: _PushingRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Declare a Grand Hand instead of the Ramsch, before looking at the skat, in the stage before a Ramsch.

        Use it only at a table whose `options.ramsch.pushing.grand_hand` is "allowed", when `hand.pushing` in the answer
        of read_table or the state of your table's view is set, `hand.pushing.turn_seat` is the seat of the caller's
        own chair and `hand.pushing.stage` is "choosing"; the other choices then are ramsch_take_skat and
        ramsch_push_skat. The table id and the version come from that answer. The caller plays alone as declarer at the
        lowest bid and the Ramsch is off: the skat stays unseen, the pushes so far count for nothing, the game is a
        Grand Hand played and scored as any other, announces nothing and starts at once (`hand.declaring`, then
        `hand.playing`). The command id names this step: the same id with the same version is a retry that changes
        nothing twice. A refusal (for example stale-version, wrong-phase, not-your-turn, out-of-order) comes back as a
        failed result with its reason, leaves the table as it was and spends the command id: the next attempt takes a
        new command id. At a table that does not allow it the reason is wrong-phase.
        """
        return await take_step(table_id, body, request, response, PushingKind.GRAND_HAND, ())


def create_pushing_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    take_step = _step_taker(tables, presence)
    _add_take(router, take_step)
    _add_put_back(router, take_step)
    _add_push(router, take_step)
    _add_declare_grand_hand(router, take_step)
    return router
