from functools import partial
from typing import TYPE_CHECKING, Annotated, Final, Literal

from fastapi import APIRouter, Body, Request, Response
from pydantic import Field

from skat.table.auction import AuctionAction, AuctionCommand
from skat.web.mcp import Exclusion, excluded
from skat.web.tables import COMMAND_RESPONSES, TABLES_PATH, CreateTableRequest, TableAnswer, actor_of, command_answer

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A bid, hold, pass or play on a table's auction: `TABLES_PATH/{table_id}` plus this.
TABLE_AUCTION_SUFFIX: Final = "/auction"


class _AuctionStepRequest(CreateTableRequest):
    """A client names only the step and the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]


class BidRequest(_AuctionStepRequest):
    action: Literal[AuctionAction.BID]
    value: Annotated[int, Field(strict=True)]


class HoldRequest(_AuctionStepRequest):
    action: Literal[AuctionAction.HOLD]


class PassRequest(_AuctionStepRequest):
    action: Literal[AuctionAction.PASS]


class PlayRequest(_AuctionStepRequest):
    action: Literal[AuctionAction.PLAY]


type AuctionStepRequest = BidRequest | HoldRequest | PassRequest | PlayRequest


def create_auction_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AUCTION_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.UNION_BODY),
    )
    async def take_auction_step(
        table_id: str,
        body: Annotated[AuctionStepRequest, Body(discriminator="action")],
        request: Request,
        response: Response,
    ) -> Response | TableAnswer:
        command = AuctionCommand(
            command_id=body.command_id,
            table_id=table_id,
            version=body.version,
            action=body.action,
            value=body.value if isinstance(body, BidRequest) else None,
        )
        return await command_answer(
            partial(
                tables.take_auction_step,
                actor_of(request),
                command,
                on_hand_ended=partial(presence.restart_leaves, table_id),
            ),
            presence,
            table_id,
            response,
        )

    return router
