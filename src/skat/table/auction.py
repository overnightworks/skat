from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import Bid, Hold, Pass, Play, auction_step
from skat.engine.deal import positions_from
from skat.table.hand_state import auction_of
from skat.table.records import Decision, Refusal
from skat.table.rules import hand_runs, seat_of

if TYPE_CHECKING:
    from skat.engine.bidding import AuctionStep
    from skat.engine.deal import Position
    from skat.table.records import Actor, TableRecord

AUCTION_STEP_COMMAND: Final = "auction-step"


class AuctionAction(StrEnum):
    BID = "bid"
    HOLD = "hold"
    PASS_ = "pass"
    PLAY = "play"


_STEPS_WITHOUT_VALUE: Final = {AuctionAction.HOLD: Hold, AuctionAction.PASS_: Pass, AuctionAction.PLAY: Play}
_ACTION_OF_STEP: Final = {
    Bid: AuctionAction.BID,
    Hold: AuctionAction.HOLD,
    Pass: AuctionAction.PASS_,
    Play: AuctionAction.PLAY,
}


@dataclass(frozen=True)
class AuctionCommand:
    """A step in the auction; the actor's seat and position come from the session, never from the client."""

    command_id: str
    table_id: str
    version: int
    action: AuctionAction
    value: int | None


def step_of(action: AuctionAction, value: int | None, position: Position) -> AuctionStep:
    """The engine's step for an action; only a bid carries a value, as the body and the stored check guarantee."""
    if value is not None:
        return Bid(position, value)
    return _STEPS_WITHOUT_VALUE[action](position)


def action_of(step: AuctionStep) -> AuctionAction:
    return _ACTION_OF_STEP[type(step)]


def auction_payload(command: AuctionCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    value = "" if command.value is None else command.value
    return f"{command.table_id}:{command.version}:{command.action.value}:{value}"


def decide_step(table: TableRecord, actor: Actor, command: AuctionCommand) -> Decision:
    """One step of the auction: no hand, then no chair, then a stale version, then the engine's reason."""
    if table.dealer is None or not hand_runs(table):
        return Decision(table, Refusal.NO_HAND)
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    if command.version != table.version:
        return Decision(table, Refusal.STALE_VERSION)
    step = step_of(command.action, command.value, positions_from(table.dealer)[chair.seat])
    outcome = auction_step(auction_of(table), step)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    steps = (*table.progress.auction, step)
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, auction=steps)))
