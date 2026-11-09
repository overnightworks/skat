from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skat.engine.deal import Position
from skat.engine.games import GameKind
from skat.engine.play import legal_cards, trick_winner

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skat.engine.cards import Card
    from skat.engine.deal import Deal
    from skat.engine.declaration import Declaring

_TRICK_SIZE: Final = 3
_TRICKS_IN_A_GAME: Final = 10
_WINNING_POINTS: Final = 61
ALL_POINTS: Final = 120
_SCHNEIDER_POINTS: Final = 30
_PLAY_ORDER: Final = tuple(Position)


def opponents_points_of(declarer_points: int) -> int:
    """The card points the opponents hold when the declarer holds `declarer_points`."""
    return ALL_POINTS - declarer_points


def _position_after(leader: Position, places: int) -> Position:
    """The position that many places after the leader in the order of play."""
    return _PLAY_ORDER[(_PLAY_ORDER.index(leader) + places) % len(_PLAY_ORDER)]


class PlayRefusal(StrEnum):
    """Why a card changed nothing, in the order the reasons are checked."""

    OVER = "over"
    NOT_YOUR_TURN = "not-your-turn"
    NOT_IN_HAND = "not-in-hand"
    MUST_FOLLOW = "must-follow"


def _kind_of(declared: Declaring) -> GameKind:
    if declared.declaration is None:
        message = "play starts after the declaration"
        raise ValueError(message)
    return declared.declaration.kind


@dataclass(frozen=True)
class CompletedTrick:
    leader: Position
    cards: tuple[Card, Card, Card]
    taker: Position


@dataclass(frozen=True)
class Sides:
    """One count for the declarer and one for the two opponents together."""

    declarer: int
    opponents: int


@dataclass(frozen=True)
class Tally:
    """Each side's tricks taken so far and the card points in them; the skat is not in it."""

    tricks: Sides
    points: Sides


def _tally(declarer: Position, tricks: tuple[CompletedTrick, ...]) -> Tally:
    taken = [trick for trick in tricks if trick.taker is declarer]
    lost = [trick for trick in tricks if trick.taker is not declarer]
    return Tally(
        tricks=Sides(declarer=len(taken), opponents=len(lost)),
        points=Sides(
            declarer=sum(card.points for trick in taken for card in trick.cards),
            opponents=sum(card.points for trick in lost for card in trick.cards),
        ),
    )


@dataclass(frozen=True)
class PlayedOut:
    """The finished game: the ended declaration state and its ten tricks, the rest derived."""

    declared: Declaring
    tricks: tuple[CompletedTrick, ...]

    @property
    def tally(self) -> Tally:
        return _tally(self.declared.declarer, self.tricks)

    @property
    def declarer_tricks(self) -> int:
        return self.tally.tricks.declarer

    @property
    def opponents_tricks(self) -> int:
        return self.tally.tricks.opponents

    @property
    def declarer_points(self) -> int:
        """The declarer's tricks plus the skat, which counts for the declarer in every game."""
        return sum(card.points for card in self.declared.skat) + self.tally.points.declarer

    @property
    def opponents_points(self) -> int:
        return opponents_points_of(self.declarer_points)

    @property
    def won_by_play(self) -> bool:
        if _kind_of(self.declared) is GameKind.NULL:
            return self.declarer_tricks == 0
        return self.declarer_points >= _WINNING_POINTS

    @property
    def declarer_schneider(self) -> bool:
        return self.declarer_points <= _SCHNEIDER_POINTS

    @property
    def opponents_schneider(self) -> bool:
        return self.opponents_points <= _SCHNEIDER_POINTS

    @property
    def declarer_schwarz(self) -> bool:
        return self.declarer_tricks == 0

    @property
    def opponents_schwarz(self) -> bool:
        return self.opponents_tricks == 0


@dataclass(frozen=True)
class CardPlayed:
    position: Position
    card: Card


@dataclass(frozen=True)
class Playing:
    """The ten tricks in progress; the result is empty until the tenth trick is taken."""

    declared: Declaring
    hands: Mapping[Position, tuple[Card, ...]]
    leader: Position
    current: tuple[Card, ...]
    tricks: tuple[CompletedTrick, ...]
    result: PlayedOut | None

    @property
    def turn(self) -> Position:
        return _position_after(self.leader, len(self.current))

    @property
    def tally(self) -> Tally:
        return _tally(self.declared.declarer, self.tricks)

    @property
    def current_plays(self) -> tuple[CardPlayed, ...]:
        """The cards of the trick in progress, each with the position that played it, in playing order."""
        return tuple(CardPlayed(_position_after(self.leader, place), card) for place, card in enumerate(self.current))


@dataclass(frozen=True)
class PlayOutcome:
    """The state after a card; a refusal leaves it as it was."""

    state: Playing
    refusal: PlayRefusal | None = None


def start_play(declared: Declaring, deal: Deal) -> Playing:
    _kind_of(declared)
    hands = {**deal.hands, declared.declarer: declared.hand}
    return Playing(
        declared=declared,
        hands=MappingProxyType(hands),
        leader=Position.FOREHAND,
        current=(),
        tricks=(),
        result=None,
    )


def _refusal(state: Playing, position: Position, card: Card) -> PlayRefusal | None:
    if state.result is not None:
        return PlayRefusal.OVER
    if position is not state.turn:
        return PlayRefusal.NOT_YOUR_TURN
    hand = state.hands[position]
    if card not in hand:
        return PlayRefusal.NOT_IN_HAND
    first = state.current[0] if state.current else None
    if card not in legal_cards(hand, first, _kind_of(state.declared)):
        return PlayRefusal.MUST_FOLLOW
    return None


def _complete_trick(state: Playing, cards: tuple[Card, Card, Card]) -> CompletedTrick:
    taker = _position_after(state.leader, trick_winner(cards, _kind_of(state.declared)))
    return CompletedTrick(state.leader, cards, taker)


def play_card(state: Playing, position: Position, card: Card) -> PlayOutcome:
    refusal = _refusal(state, position, card)
    if refusal is not None:
        return PlayOutcome(state, refusal)
    hands = {**state.hands, position: tuple(each for each in state.hands[position] if each != card)}
    current = (*state.current, card)
    if len(current) < _TRICK_SIZE:
        return PlayOutcome(replace(state, hands=MappingProxyType(hands), current=current))
    trick = _complete_trick(state, (current[0], current[1], current[2]))
    tricks = (*state.tricks, trick)
    result = PlayedOut(state.declared, tricks) if len(tricks) == _TRICKS_IN_A_GAME else None
    return PlayOutcome(
        replace(state, hands=MappingProxyType(hands), leader=trick.taker, current=(), tricks=tricks, result=result)
    )


def playing_after(start: Playing, steps: tuple[CardPlayed, ...]) -> Playing:
    """The state a stored log of played cards leads to; a log the rules refuse is corrupt and raises."""
    state = start
    for place, step in enumerate(steps, start=1):
        outcome = play_card(state, step.position, step.card)
        if outcome.refusal is not None:
            message = f"impossible card log: step {place} refused: {outcome.refusal.value}"
            raise ValueError(message)
        state = outcome.state
    return state
