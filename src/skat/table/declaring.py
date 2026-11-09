from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.cards import DECK
from skat.engine.deal import positions_from
from skat.engine.declaration import DeclaringStep, PutBack, TakeSkat, declaring_step
from skat.table.hand_state import declaring_of
from skat.table.records import Decision, Refusal
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.declaration import Declaration, Declaring, Stage
    from skat.table.records import Actor, TableRecord

DECLARING_STEP_COMMAND: Final = "declaring-step"


@dataclass(frozen=True)
class DeclaringCommand:
    """A step of the declarer; the actor's seat and position come from the session, never from the client."""

    command_id: str
    table_id: str
    version: int
    step: DeclaringStep


@dataclass(frozen=True)
class DeclaringView:
    """The declarer's steps as every viewer may see them: the game once declared, its cards once it is ouvert."""

    declarer_seat: int
    stage: Stage
    declaration: Declaration | None
    open_cards: tuple[Card, ...]


def _step_text(step: DeclaringStep) -> str:
    if isinstance(step, TakeSkat):
        return "take"
    if isinstance(step, PutBack):
        return "put-back:" + ",".join(card_text(card) for card in step.cards)
    return f"declare:{step.kind.name}:{step.hand}:{step.ouvert}:{step.announcement.value}"


def declaring_payload(command: DeclaringCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}:{_step_text(command.step)}"


def decide_declaring_step(table: TableRecord, actor: Actor, command: DeclaringCommand) -> Decision:
    """One step of the declarer: no hand, no chair, a stale version, no declarer yet, not the declarer, the engine."""
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = declaring_of(table)
    if state is None:
        return Decision(table, Refusal.WRONG_PHASE)
    if state.declarer is not position:
        return Decision(table, Refusal.NOT_DECLARER)
    outcome = declaring_step(state, command.step)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    steps = (*table.progress.declaring, command.step)
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, declaring=steps)))


def declaring_view_of(state: Declaring | None, dealer: int) -> DeclaringView | None:
    """The declaring state for every viewer alike; None while the auction has no declarer."""
    if state is None:
        return None
    seats = {position: seat for seat, position in positions_from(dealer).items()}
    open_cards = state.hand if state.declaration is not None and state.declaration.ouvert else ()
    return DeclaringView(
        declarer_seat=seats[state.declarer],
        stage=state.stage,
        declaration=state.declaration,
        open_cards=tuple(card for card in DECK if card in open_cards),
    )
