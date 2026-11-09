from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skat.engine.deal import Position
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind
from skat.engine.play import legal_cards, trick_winner
from skat.engine.replay import replay_log

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skat.engine.cards import Card
    from skat.engine.deal import Deal
    from skat.engine.declaration import Declaration, Declaring

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
    ALREADY_WON = "already-won"
    NEEDS_CONSENT = "needs-consent"


class Ending(StrEnum):
    """How a game ended: with its tenth trick, by the declarer giving it up, by a side throwing its cards down,
    by an opponent giving it up, or at the trick that decided it.

    A trick decides a Null game when its declarer takes it, and a game announced Schwarz when the opponents take it;
    the game is then `DECIDED` against the declarer. An opponent's give-up is `OPPONENT_GAVE_UP` when the game was
    already won for the declarer, `DECIDED` when it was already lost for him and `CONCEDED` when it was undecided,
    which is valued by its declaration and bid.
    """

    PLAYED_OUT = "played-out"
    GIVEN_UP = "given-up"
    DECLARER_THREW_DOWN = "declarer-threw-down"
    OPPONENTS_THREW_DOWN = "opponents-threw-down"
    DECIDED = "decided"
    OPPONENT_GAVE_UP = "opponent-gave-up"
    CONCEDED = "conceded"


_REST_COUNTS_FOR_DECLARER: Final = frozenset({Ending.OPPONENTS_THREW_DOWN, Ending.DECIDED})


def _declaration_of(declared: Declaring) -> Declaration:
    if declared.declaration is None:
        message = "play starts after the declaration"
        raise ValueError(message)
    return declared.declaration


def _kind_of(declared: Declaring) -> GameKind:
    return _declaration_of(declared).kind


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
    """The finished game: the ended declaration state and its completed tricks, the rest derived.

    A trick not completed when the game ended counts for the opponents,
    or for the declarer when the opponents threw down or the game ended decided against him:
    then the opponents keep only the tricks and points they completed.
    """

    declared: Declaring
    tricks: tuple[CompletedTrick, ...]
    ending: Ending = Ending.PLAYED_OUT

    @property
    def tally(self) -> Tally:
        return _tally(self.declared.declarer, self.tricks)

    @property
    def _opponents_keep_only_their_completed_tricks(self) -> bool:
        return self.ending in _REST_COUNTS_FOR_DECLARER

    @property
    def _tricks_left(self) -> int:
        return _TRICKS_IN_A_GAME - len(self.tricks)

    @property
    def declarer_tricks(self) -> int:
        if self._opponents_keep_only_their_completed_tricks:
            return self.tally.tricks.declarer + self._tricks_left
        return self.tally.tricks.declarer

    @property
    def opponents_tricks(self) -> int:
        if self._opponents_keep_only_their_completed_tricks:
            return self.tally.tricks.opponents
        return self.tally.tricks.opponents + self._tricks_left

    @property
    def declarer_points(self) -> int:
        """The declarer's tricks plus the skat, which counts for the declarer in every game.

        When the opponents keep only their completed tricks, every point outside them is his.
        """
        if self._opponents_keep_only_their_completed_tricks:
            return opponents_points_of(self.tally.points.opponents)
        return sum(card.points for card in self.declared.skat) + self.tally.points.declarer

    @property
    def opponents_points(self) -> int:
        return opponents_points_of(self.declarer_points)

    @property
    def won_by_play(self) -> bool:
        if self.ending is Ending.GIVEN_UP:
            return False
        if _kind_of(self.declared) is GameKind.NULL:
            return self.ending is not Ending.DECLARER_THREW_DOWN and self.tally.tricks.declarer == 0
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
    """The ten tricks in progress; the result is empty until the tenth trick is taken or the game ends early."""

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


def _decides_the_game(declared: Declaring, trick: CompletedTrick) -> bool:
    """A Null game is decided by the declarer's first trick, a game announced Schwarz by the opponents' first."""
    taken_by_declarer = trick.taker is declared.declarer
    if _kind_of(declared) is GameKind.NULL:
        return taken_by_declarer
    return not taken_by_declarer and _declaration_of(declared).announcement is Announcement.SCHWARZ


def _result_after(declared: Declaring, tricks: tuple[CompletedTrick, ...]) -> PlayedOut | None:
    """The tenth trick ends every game; before it only the trick just completed can decide one."""
    if len(tricks) == _TRICKS_IN_A_GAME:
        return PlayedOut(declared, tricks)
    if _decides_the_game(declared, tricks[-1]):
        return PlayedOut(declared, tricks, Ending.DECIDED)
    return None


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
    return PlayOutcome(
        replace(
            state,
            hands=MappingProxyType(hands),
            leader=trick.taker,
            current=(),
            tricks=tricks,
            result=_result_after(state.declared, tricks),
        )
    )


def playing_after(start: Playing, steps: tuple[CardPlayed, ...]) -> Playing:
    return replay_log(start, steps, lambda state, step: play_card(state, step.position, step.card), "card")
