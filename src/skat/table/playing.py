from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.cards import DECK
from skat.engine.deal import seats_from
from skat.engine.tricks import CardPlayed, play_card
from skat.table.game_list import list_entry_of
from skat.table.hand_state import playing_of
from skat.table.records import Decision, HandProgress, Refusal, TableRecord
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.tricks import PlayedOut, Playing, Sides
    from skat.table.records import Actor

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
    """The last completed trick: its cards in playing order from the seat that led it, and who took it."""

    cards: tuple[Card, ...]
    leader_seat: int
    taker_seat: int


@dataclass(frozen=True)
class PlayingView:
    """The game in play as one viewer may see it; the turn is the seat that plays next."""

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
    if outcome.state.result is None:
        return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, plays=plays)))
    return Decision(_ended(table, outcome.state.result))


def _ended(table: TableRecord, played: PlayedOut) -> TableRecord:
    """The tenth trick ends the hand: its cards and steps go, its entry joins the list, the chairs stay."""
    return TableRecord(
        id=table.id,
        version=table.version + 1,
        chairs=table.chairs,
        dealer=table.dealer,
        hand=None,
        progress=HandProgress(),
        game_list=(*table.game_list, list_entry_of(played, table)),
    )


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
    seats = seats_from(dealer)
    last = state.tricks[-1] if state.tricks else None
    return PlayingView(
        turn_seat=seats[state.turn],
        current_trick=tuple(SeatedCard(seats[play.position], play.card) for play in state.current_plays),
        last_trick=None if last is None else LastTrick(last.cards, seats[last.leader], seats[last.taker]),
        tricks_won=state.tally.tricks,
        trick_points=state.tally.points,
        legal_cards=_legal_cards(state, viewer_positions),
    )
