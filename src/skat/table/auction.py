from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import (
    LOWEST_BID,
    VALID_BIDS,
    Auction,
    Awaiting,
    Bid,
    Declared,
    Hold,
    Pass,
    Play,
    auction_step,
)
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
    PASS = "pass"  # noqa: S105 - the word for dropping out of the auction and no password
    PLAY = "play"


_STEPS_WITHOUT_VALUE: Final = {AuctionAction.HOLD: Hold, AuctionAction.PASS: Pass, AuctionAction.PLAY: Play}
_ACTION_OF_STEP: Final = {
    Bid: AuctionAction.BID,
    Hold: AuctionAction.HOLD,
    Pass: AuctionAction.PASS,
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


@dataclass(frozen=True)
class AuctionWord:
    """A chair's latest word; a hold carries the standing bid it answered, a pass no value."""

    seat: int
    action: AuctionAction
    value: int | None


@dataclass(frozen=True)
class AuctionDeclared:
    seat: int
    value: int


@dataclass(frozen=True)
class AuctionView:
    """The auction as one viewer may see it; `values` lists what the viewer may bid, only on their turn to bid."""

    turn_seat: int | None
    awaiting: Awaiting | None
    standing: int | None
    values: tuple[int, ...]
    words: tuple[AuctionWord, ...]
    declared: AuctionDeclared | None


def _word_value(step: AuctionStep, standing: int | None) -> int | None:
    if isinstance(step, Bid):
        return step.value
    if isinstance(step, Hold):
        return standing
    if isinstance(step, Play):
        return LOWEST_BID
    return None


def _words(steps: tuple[AuctionStep, ...], seats: dict[Position, int]) -> tuple[AuctionWord, ...]:
    """Each chair's latest word in seat order, folded over the stored steps because the engine keeps no history."""
    latest: dict[int, AuctionWord] = {}
    auction = Auction.start()
    for step in steps:
        seat = seats[step.position]
        latest[seat] = AuctionWord(seat, action_of(step), _word_value(step, auction.standing))
        auction = auction_step(auction, step).auction
    return tuple(latest[seat] for seat in sorted(latest))


def auction_view_of(table: TableRecord, viewer_account_id: str) -> AuctionView:
    """The running hand's auction for one account; only the viewer whose turn it is to bid is told the values."""
    # The store writes the dealer with the hand, so a hand without a dealer is a wiring fault.
    if table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} holds an auction and no dealer"
        raise RuntimeError(message)
    seats = {position: seat for seat, position in positions_from(table.dealer).items()}
    auction = auction_of(table)
    viewer = seat_of(table, viewer_account_id)
    running = auction.result is None
    my_turn_to_bid = (
        running and auction.awaiting is Awaiting.BID and viewer is not None and viewer.seat == seats[auction.actor]
    )
    standing = auction.standing
    return AuctionView(
        turn_seat=seats[auction.actor] if running else None,
        awaiting=auction.awaiting if running else None,
        standing=standing,
        values=tuple(value for value in VALID_BIDS if standing is None or value > standing) if my_turn_to_bid else (),
        words=_words(table.progress.auction, seats),
        declared=None
        if not isinstance(auction.result, Declared)
        else AuctionDeclared(seats[auction.result.declarer], auction.result.value),
    )
