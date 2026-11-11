from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.deal import seats_from
from skat.engine.declaration import Stage
from skat.engine.schieberamsch import GrandHandRule, Push, PushOptions, Put, Take, pushing_step
from skat.table.game_list import pushes_factor
from skat.table.hand_state import pushing_of
from skat.table.records import Decision, Refusal
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.schieberamsch import Pushing
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
    """The stage as every viewer may see it: whose turn it is, whether that seat may still take the skat or must put
    two cards back, who finished their turn, and what the pushes so far multiply the Ramsch's score by. It names no
    card.
    """

    turn_seat: int
    stage: Stage
    moves: tuple[PushingMove, ...]
    factor: int


def pushing_payload(command: PushingCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    cards = ",".join(card_text(card) for card in command.cards)
    return f"{command.table_id}:{command.version}:{command.kind.value}:{cards}"


def _step_of(command: PushingCommand, position: Position) -> PushingStep:
    if command.kind is PushingKind.TAKE:
        return Take(position)
    if command.kind is PushingKind.PUT_BACK:
        return Put(position, command.cards)
    return Push(position)


def decide_pushing_step(table: TableRecord, actor: Actor, command: PushingCommand) -> Decision:
    """One step of the stage: no hand, no chair, a stale version, no stage running, then the engine's reason."""
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = pushing_of(table)
    ramsch = table.options.ramsch
    if state is None or state.result is not None or ramsch is None or ramsch.pushing is None:
        return Decision(table, Refusal.WRONG_PHASE)
    step = _step_of(command, position)
    outcome = pushing_step(state, step, PushOptions(ramsch.pushing, GrandHandRule.OFF))
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


def pushing_view_of(
    state: Pushing | None, options: TableOptions, steps: tuple[PushingStep, ...], dealer: int
) -> PushingView | None:
    """The stage for every viewer alike; None unless a stage runs, which no Ramsch without pushing has and none has
    once its first card may be played.
    """
    ramsch = options.ramsch
    if state is None or ramsch is None or ramsch.pushing is None or state.result is not None:
        return None
    return PushingView(
        turn_seat=seats_from(dealer)[state.turn],
        stage=Stage.DISCARDING if state.holds_twelve else Stage.CHOOSING,
        moves=_moves_of(steps, dealer),
        factor=pushes_factor(state.pushes, options),
    )
