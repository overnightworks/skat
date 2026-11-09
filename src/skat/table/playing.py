from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.tricks import CardPlayed, play_card
from skat.table.hand_state import playing_of
from skat.table.records import Decision, Refusal
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.table.records import Actor, TableRecord

PLAY_CARD_COMMAND: Final = "play-card"


@dataclass(frozen=True)
class PlayCardCommand:
    """A card played; the actor's seat and position come from the session, never from the client."""

    command_id: str
    table_id: str
    version: int
    card: Card


def card_payload(command: PlayCardCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}:{card_text(command.card)}"


def decide_card(table: TableRecord, actor: Actor, command: PlayCardCommand) -> Decision:
    """One card: no hand, no chair, a stale version, the wrong phase, then the engine's reason."""
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = playing_of(table)
    if state is None:
        return Decision(table, Refusal.WRONG_PHASE)
    outcome = play_card(state, position, command.card)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    plays = (*table.progress.plays, CardPlayed(position, command.card))
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, plays=plays)))
