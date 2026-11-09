from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.cards import DECK
from skat.engine.deal import positions_from
from skat.engine.tricks import CardPlayed, play_card
from skat.table.hand_state import playing_of
from skat.table.records import Decision, Refusal
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.tricks import CompletedTrick, Playing
    from skat.table.records import Actor, TableRecord

PLAY_CARD_COMMAND: Final = "play-card"


@dataclass(frozen=True)
class PlayCardCommand:
    """A card played; the actor's seat and position come from the session, never from the client."""

    command_id: str
    table_id: str
    version: int
    card: Card


@dataclass(frozen=True)
class SeatedCard:
    """A card of the trick in progress and the seat that played it."""

    seat: int
    card: Card


@dataclass(frozen=True)
class LastTrick:
    """The last completed trick: its cards in playing order and who took it."""

    cards: tuple[Card, ...]
    taker_seat: int


@dataclass(frozen=True)
class Sides:
    declarer: int
    opponents: int


@dataclass(frozen=True)
class PlayingView:
    """The game in play as one viewer may see it; the turn is None once all thirty cards are played."""

    turn_seat: int | None
    current_trick: tuple[SeatedCard, ...]
    last_trick: LastTrick | None
    tricks_won: Sides
    trick_points: Sides
    legal_cards: tuple[Card, ...]


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


def _sides(state: Playing, measure: Callable[[CompletedTrick], int]) -> Sides:
    declarer = state.declared.declarer
    return Sides(
        declarer=sum(measure(trick) for trick in state.tricks if trick.taker is declarer),
        opponents=sum(measure(trick) for trick in state.tricks if trick.taker is not declarer),
    )


def _trick_points(trick: CompletedTrick) -> int:
    return sum(card.points for card in trick.cards)


def _legal_cards(state: Playing, viewer_positions: frozenset[Position]) -> tuple[Card, ...]:
    """The cards the engine accepts from the player on turn, in deck order, for that player alone."""
    turn = state.turn
    if turn not in viewer_positions:
        return ()
    held = state.hands[turn]
    return tuple(card for card in DECK if card in held and play_card(state, turn, card).refusal is None)


def playing_view_of(state: Playing | None, dealer: int, viewer_positions: frozenset[Position]) -> PlayingView | None:
    """The game in play for one viewer; None until the game is declared.

    Everyone sees the turn, the trick in progress, the last completed trick and both sides' tricks and trick
    points, which leave out the skat. Only the seated player on turn gets the cards they may play.
    """
    if state is None:
        return None
    seats = {position: seat for seat, position in positions_from(dealer).items()}
    last = state.tricks[-1] if state.tricks else None
    return PlayingView(
        turn_seat=None if state.result is not None else seats[state.turn],
        current_trick=tuple(SeatedCard(seats[play.position], play.card) for play in state.current_plays),
        last_trick=None if last is None else LastTrick(last.cards, seats[last.taker]),
        tricks_won=_sides(state, lambda _trick: 1),
        trick_points=_sides(state, _trick_points),
        legal_cards=_legal_cards(state, viewer_positions),
    )
