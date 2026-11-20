from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, Annotated, Final, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.auction_plans import AuctionPlanCommand
from skat.table.records import AuctionPlan, BidLimit, PassAhead, PlanMode
from skat.web.mcp import (
    AUCTION_BID_MARK,
    AUCTION_HOLD_MARK,
    AUCTION_PASS_MARK,
    AUCTION_PLAY_MARK,
    Exclusion,
    excluded,
)
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLES_PATH,
    CommandRequest,
    PlanKind,
    TableAnswer,
    TableIdInPath,
    TableVersion,
    actor_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A bid, hold, pass or play on a table's auction: `TABLES_PATH/{table_id}` plus the step's suffix.
TABLE_AUCTION_BID_SUFFIX: Final = "/auction/bid"
TABLE_AUCTION_HOLD_SUFFIX: Final = "/auction/hold"
TABLE_AUCTION_PASS_SUFFIX: Final = "/auction/pass"  # noqa: S105 - the word for dropping out of the auction and no password
TABLE_AUCTION_PLAY_SUFFIX: Final = "/auction/play"
# A player's own plan for the auction: `TABLES_PATH/{table_id}` plus this.
TABLE_AUCTION_PLAN_SUFFIX: Final = "/auction/plan"


class _AuctionStepRequest(CommandRequest):
    """A client names only the step and the version it saw: its seat and position come from the session."""

    version: TableVersion


class BidRequest(_AuctionStepRequest):
    value: Annotated[int, Field(strict=True)]


class _LimitBody(BaseModel):
    """A limit: one value of the bid ladder, `ask` unless the player fixes it."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[PlanKind.LIMIT]
    value: Annotated[int, Field(strict=True)]
    mode: PlanMode = PlanMode.ASK


class _PassAheadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[PlanKind.PASS]


_PlanBody = Annotated[_LimitBody | _PassAheadBody, Field(discriminator="kind")]


class AuctionPlanRequest(CommandRequest):
    """A player's plan, or null to take it back: no version, since a plan made off turn must not race another player's
    step; its seat comes from the session.
    """

    plan: _PlanBody | None


def _plan_of(body: _LimitBody | _PassAheadBody | None) -> AuctionPlan | None:
    if body is None:
        return None
    return BidLimit(body.value, body.mode) if isinstance(body, _LimitBody) else PassAhead()


type StepTaker = Callable[
    [str, _AuctionStepRequest, Request, Response, AuctionAction], Awaitable[Response | TableAnswer]
]


def _step_taker(tables: TableService, presence: Presence) -> StepTaker:
    async def take_step(
        table_id: TableIdInPath, body: _AuctionStepRequest, request: Request, response: Response, action: AuctionAction
    ) -> Response | TableAnswer:
        command = AuctionCommand(
            command_id=body.command_id,
            table_id=table_id,
            version=body.version,
            action=action,
            value=body.value if isinstance(body, BidRequest) else None,
        )
        return await command_answer(
            partial(tables.take_auction_step, actor_of(request), command),
            presence,
            table_id,
            response,
        )

    return take_step


def _add_bid(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AUCTION_BID_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AUCTION_BID_MARK,
    )
    async def bid(
        table_id: TableIdInPath, body: BidRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Bid a value in the auction of a Skat table, on the caller's turn as the bidder.

        Use it when `hand.auction.awaiting` in the answer of read_table or the state of your table's view is "bid" and
        it is the caller's turn. The value comes from `hand.auction.values`. Refused: a stale version, a value that is
        not above the standing one, not the caller's turn.
        """
        return await take_step(table_id, body, request, response, AuctionAction.BID)


def _add_hold(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AUCTION_HOLD_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AUCTION_HOLD_MARK,
    )
    async def hold(
        table_id: TableIdInPath, body: _AuctionStepRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Hold the bid that stands in the auction of a Skat table, on the caller's turn as the responder.

        Use it when `hand.auction.awaiting` in the answer of read_table or the state of your table's view is "answer"
        and it is the caller's turn. Refused: a stale version, not the caller's turn, a hold where a bid is awaited.
        """
        return await take_step(table_id, body, request, response, AuctionAction.HOLD)


def _add_pass(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AUCTION_PASS_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AUCTION_PASS_MARK,
    )
    async def pass_(
        table_id: TableIdInPath, body: _AuctionStepRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Pass in the auction of a Skat table: the caller is out and takes no further step of it.

        Use it on the caller's turn, whatever `hand.auction.awaiting` in the answer of read_table or the state of your
        table's view holds: no value of it names a pass. Refused: a stale version, not the caller's turn, already
        passed.
        """
        return await take_step(table_id, body, request, response, AuctionAction.PASS)


def _add_play(router: APIRouter, take_step: StepTaker) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AUCTION_PLAY_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AUCTION_PLAY_MARK,
    )
    async def play(
        table_id: TableIdInPath, body: _AuctionStepRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Play the lowest game value as the forehand, once both others passed, to end the auction of a Skat table.

        This is the forehand's "Spielen" and no card: a card goes through play_card. Use it on the caller's turn when
        `hand.auction.awaiting` in the answer of read_table or the state of your table's view is "play". Refused: a
        stale version, not the caller's turn.
        """
        return await take_step(table_id, body, request, response, AuctionAction.PLAY)


def _add_plan(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AUCTION_PLAN_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.AUCTION_PLAN),
    )
    async def plan(
        table_id: TableIdInPath, body: AuctionPlanRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Set, change or clear the caller's private plan for the auction of a Skat table: „halten bis“ as a limit,
        fixed or ask, or „Weg“ ahead as a pass.

        The table steps for the caller as the plan says, in the same answer; only the caller's own view carries it.
        Refused: no hand, not seated, a chair waiting for a sitter, the auction over, already passed, a limit that is
        no bid value or is below the standing bid.
        """
        command = AuctionPlanCommand(command_id=body.command_id, table_id=table_id, plan=_plan_of(body.plan))
        return await command_answer(
            partial(tables.set_auction_plan, actor_of(request), command), presence, table_id, response
        )


def create_auction_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    take_step = _step_taker(tables, presence)
    _add_bid(router, take_step)
    _add_hold(router, take_step)
    _add_pass(router, take_step)
    _add_play(router, take_step)
    _add_plan(router, tables, presence)
    return router
