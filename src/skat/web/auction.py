from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.auction import AuctionAction, AuctionCommand
from skat.web.mcp import AUCTION_BID_MARK, AUCTION_HOLD_MARK, AUCTION_PASS_MARK, AUCTION_PLAY_MARK
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLES_PATH,
    CommandRequest,
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


class _AuctionStepRequest(CommandRequest):
    """A client names only the step and the version it saw: its seat and position come from the session."""

    version: TableVersion


class BidRequest(_AuctionStepRequest):
    value: Annotated[int, Field(strict=True)]


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


def create_auction_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    take_step = _step_taker(tables, presence)
    _add_bid(router, take_step)
    _add_hold(router, take_step)
    _add_pass(router, take_step)
    _add_play(router, take_step)
    return router
