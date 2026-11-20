"""The runner of the auction plans: the one place that steps the auction for a seat that made a plan.

A seat's plan is its private „halten bis“ or „Weg“ said ahead. The runner takes the plan's step whenever the auction
awaits that seat, in the same decision that made the seat's turn: after a step of the auction, after the plan is set and
after a sit that ends the wait for a sitter. It sits above the rules of the table and its auction, which know no plan
but a chair that changes hands.
"""

import hashlib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import VALID_BIDS, Awaiting, Bid, BidRefusal, Hold, Pass
from skat.engine.deal import seats_from
from skat.table.auction import apply_step
from skat.table.hand_state import auction_of
from skat.table.records import BidLimit, Decision, PassAhead, PlanMode, Refusal, SeatPlan
from skat.table.rules import acting_position, decide_sit, hand_runs, seat_of, waiting_seat_of

if TYPE_CHECKING:
    from datetime import datetime

    from skat.engine.bidding import Auction, AuctionStep
    from skat.table.records import Actor, AuctionPlan, NewHand, TableRecord

AUCTION_PLAN_COMMAND: Final = "auction-plan"


@dataclass(frozen=True)
class AuctionPlanCommand:
    """A seated player's plan for the auction, or None to take it back; the seat comes from the session and no version
    is named, since a plan made off turn changes nothing another player's step depends on.
    """

    command_id: str
    table_id: str
    plan: AuctionPlan | None


def plan_payload(command: AuctionPlanCommand) -> str:
    """The receipt's payload: a digest of the plan, since the limit is private and lives only in the plan's own table,
    so a retry under the same id with another plan is another request.
    """
    if command.plan is None:
        return f"{command.table_id}:clear"
    plan = command.plan
    text = "pass" if isinstance(plan, PassAhead) else f"limit:{plan.value}:{plan.mode.value}"
    return f"{command.table_id}:{hashlib.sha256(text.encode()).hexdigest()}"


def plan_step_at_play(plan: AuctionPlan) -> bool:
    """Whether the plan steps for forehand's choice after two passes: a pass ahead passes, so the hand he said „Weg“ to
    is thrown in; a limit names no game to play and takes no step.
    """
    return isinstance(plan, PassAhead)


def _reach(auction: Auction) -> int | None:
    """The value the seat on turn must stand at to stay in: the bid it answers, or the next bid it would name; None
    when the ladder has no higher bid.
    """
    standing = auction.standing
    if auction.awaiting is Awaiting.ANSWER:
        return standing
    return next((value for value in VALID_BIDS if standing is None or value > standing), None)


def _limit_step(limit: BidLimit, auction: Auction) -> AuctionStep | None:
    position, reach = auction.actor, _reach(auction)
    if reach is None or reach > limit.value:
        return Pass(position) if limit.mode is PlanMode.FIXED else None
    return Hold(position) if auction.awaiting is Awaiting.ANSWER else Bid(position, reach)


def _planned_step(table: TableRecord) -> AuctionStep | None:
    """The step the plan of the seat the auction awaits takes; None when that seat has no plan, its plan stops above
    its limit, or the hand cannot move.
    """
    if table.dealer is None or not hand_runs(table) or waiting_seat_of(table) is not None:
        return None
    auction = auction_of(table)
    if auction.result is not None:
        return None
    plan = table.progress.plan_of(seats_from(table.dealer)[auction.actor])
    if plan is None:
        return None
    if auction.awaiting is Awaiting.PLAY:
        return Pass(auction.actor) if plan_step_at_play(plan) else None
    if isinstance(plan, PassAhead):
        return Pass(auction.actor)
    return _limit_step(plan, auction)


def run_plans(decision: Decision) -> Decision:
    """The decision once the plans took every step they take: a refusal stays as it is, and each step is a pass or a
    higher bid, so the loop ends.
    """
    while decision.refusal is None and (step := _planned_step(decision.table)) is not None:
        decision = apply_step(decision.table, step)
    return decision


def _refusal_of(table: TableRecord, actor: Actor, plan: AuctionPlan | None) -> Refusal | BidRefusal | None:
    """Why the actor may not plan now: no hand, no chair or an open chair, an auction that is over, a seat that
    passed, a limit off the ladder or below the standing bid.
    """
    position = acting_position(table, actor, table.version)
    if isinstance(position, Refusal):
        return position
    auction = auction_of(table)
    if auction.result is not None:
        return Refusal.WRONG_PHASE
    if position in auction.passed:
        return BidRefusal.ALREADY_PASSED
    if isinstance(plan, BidLimit) and (
        plan.value not in VALID_BIDS or (auction.standing is not None and plan.value < auction.standing)
    ):
        return BidRefusal.INVALID_VALUE
    return None


def decide_set_plan(table: TableRecord, actor: Actor, command: AuctionPlanCommand) -> Decision:
    """The actor's plan replaces their earlier one, or goes when the command names none; the plan then takes the steps
    it takes, so a plan made on the actor's turn steps at once. A plan made off turn leaves the version alone.
    """
    refusal = _refusal_of(table, actor, command.plan)
    if refusal is not None:
        return Decision(table, refusal)
    chair = seat_of(table, actor.account_id)
    assert chair is not None  # noqa: S101 - narrows the type for the chair `_refusal_of` found
    others = frozenset(each for each in table.progress.plans if each.seat != chair.seat)
    plans = others if command.plan is None else others | {SeatPlan(chair.seat, command.plan)}
    return run_plans(Decision(replace(table, progress=replace(table.progress, plans=plans))))


def sit_with_plans(table: TableRecord, actor: Actor, seat: int, new_hand: NewHand | None, now: datetime) -> Decision:
    """The sit of `decide_sit`, then the steps the plans of the seated players take when the sit ended the wait for a
    sitter: the one sit both a person's sit and an agent's accept go through.
    """
    return run_plans(decide_sit(table, actor, seat, new_hand, now))
