from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.cards import DECK, Rank
from skat.engine.deal import seats_from
from skat.engine.declaration import Stage
from skat.engine.schieberamsch import DeclareGrandHand, GrandHandRule, Push, Put, Take, pushing_step
from skat.table.game_list import pushes_factor
from skat.table.hand_state import pushing_of
from skat.table.records import Decision, Refusal
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.schieberamsch import Pushing, PushOptions
    from skat.table.records import Actor, PushingStep, TableOptions, TableRecord

PUSHING_STEP_COMMAND: Final = "pushing-step"


class PushAction(StrEnum):
    """What a seat that has finished its turn of the stage did with the skat; the answer's token."""

    TOOK = "took"
    PUSHED = "pushed"


class PushingKind(StrEnum):
    """The steps a seat takes in the stage before a Ramsch."""

    TAKE = "take"
    PUT_BACK = "put-back"
    PUSH = "push"
    GRAND_HAND = "grand-hand"


@dataclass(frozen=True)
class PushingCommand:
    """A step of the stage before a Ramsch, with the cards of a put-back; the actor's seat and position come from the
    session, never from the client.
    """

    command_id: str
    table_id: str
    version: int
    kind: PushingKind
    cards: tuple[Card, ...] = ()


@dataclass(frozen=True)
class PushingMove:
    """A seat that has finished its turn of the stage and what it did."""

    seat: int
    action: PushAction


@dataclass(frozen=True)
class PushingView:
    """The stage as a viewer may see it: whose turn it is, whether that seat may still take the skat or must put two
    cards back, who finished their turn, and what the pushes so far multiply the Ramsch's score by. Only the seat on
    turn that holds twelve cards is named `put_back_cards`, the cards its rule lets it put back, in deck order, as the
    play names the cards to play; for everyone else it is empty.
    """

    turn_seat: int
    stage: Stage
    moves: tuple[PushingMove, ...]
    factor: int
    put_back_cards: tuple[Card, ...]


def pushing_payload(command: PushingCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    cards = ",".join(card_text(card) for card in command.cards)
    return f"{command.table_id}:{command.version}:{command.kind.value}:{cards}"


def _step_of(command: PushingCommand, position: Position) -> PushingStep:
    if command.kind is PushingKind.TAKE:
        return Take(position)
    if command.kind is PushingKind.PUT_BACK:
        return Put(position, command.cards)
    if command.kind is PushingKind.GRAND_HAND:
        return DeclareGrandHand(position)
    return Push(position)


def decide_pushing_step(table: TableRecord, actor: Actor, command: PushingCommand) -> Decision:
    """One step of the stage: no hand, no chair, a stale version, no stage running, a Grand Hand at a table that does
    not allow it, then the engine's reason.
    """
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = pushing_of(table)
    ramsch = table.options.ramsch
    options = None if ramsch is None else ramsch.push_options
    if state is None or state.result is not None or options is None:
        return Decision(table, Refusal.WRONG_PHASE)
    if command.kind is PushingKind.GRAND_HAND and options.grand_hand is GrandHandRule.OFF:
        return Decision(table, Refusal.WRONG_PHASE)
    step = _step_of(command, position)
    outcome = pushing_step(state, step, options)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    steps = (*table.progress.pushing, step)
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, pushing=steps)))


def _moves_of(steps: tuple[PushingStep, ...], dealer: int) -> tuple[PushingMove, ...]:
    """The seats that finished their turn, in order: a put-back ends a turn that took the skat."""
    seats = seats_from(dealer)
    return tuple(
        PushingMove(seats[step.position], PushAction.TOOK if isinstance(step, Put) else PushAction.PUSHED)
        for step in steps
        if not isinstance(step, Take)
    )


def _put_back_cards(state: Pushing, viewer_positions: frozenset[Position], options: PushOptions) -> tuple[Card, ...]:
    """The cards the seat on turn may put back after its take, for that seat alone."""
    if not state.holds_twelve or state.turn not in viewer_positions:
        return ()
    held = state.deal.hands[state.turn]
    return tuple(
        card for card in DECK if card in held and (options.pushing.lets_jacks_go or card.rank is not Rank.JACK)
    )


def pushing_view_of(
    state: Pushing | None,
    options: TableOptions,
    steps: tuple[PushingStep, ...],
    dealer: int,
    viewer_positions: frozenset[Position],
) -> PushingView | None:
    """The stage; None unless a stage runs, which no Ramsch without pushing has and none has once its first card may
    be played.
    """
    ramsch = options.ramsch
    push_options = None if ramsch is None else ramsch.push_options
    if state is None or push_options is None or state.result is not None:
        return None
    return PushingView(
        turn_seat=seats_from(dealer)[state.turn],
        stage=Stage.DISCARDING if state.holds_twelve else Stage.CHOOSING,
        moves=_moves_of(steps, dealer),
        factor=pushes_factor(state.pushes, options),
        put_back_cards=_put_back_cards(state, viewer_positions, push_options),
    )
