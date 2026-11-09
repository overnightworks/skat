from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skat.engine.deal import Position
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind, Trump
from skat.engine.play import legal_cards, trick_winner
from skat.engine.replay import replay_log

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from skat.engine.cards import Card
    from skat.engine.deal import Deal
    from skat.engine.declaration import Declaration, Declaring

_TRICK_SIZE: Final = 3
TRICKS_IN_A_GAME: Final = 10
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
    CLAIM_OUT_OF_REACH = "claim-out-of-reach"
    NEEDS_CONSENT = "needs-consent"
    NOT_AN_OPPONENT = "not-an-opponent"


class Ending(StrEnum):
    """How a game ended: with its tenth trick, by the declarer giving it up, by a side throwing its cards down,
    by an opponent giving it up or playing open, by the declarer shortening it with every opponent's yes, or at the
    trick that decided it.

    A trick decides a Null game when its declarer takes it, and a game announced Schwarz when the opponents take it;
    the game is then `DECIDED` against the declarer. A give-up or a shortening is `DECIDED_WON` when the game was
    already won for the declarer, `DECIDED` when it was already lost for him. An undecided one is `CONCEDED` after an
    opponent's give-up, valued by its declaration and bid, and `SHORTENED` after the declarer's shortening, valued by
    its declaration and the level he demanded. An opponent who plays open ends the game as `REST_TO_OPPONENTS` when
    the declarer could take no further trick, which counts the rest for the opponents.
    """

    PLAYED_OUT = "played-out"
    GIVEN_UP = "given-up"
    DECLARER_THREW_DOWN = "declarer-threw-down"
    OPPONENTS_THREW_DOWN = "opponents-threw-down"
    DECIDED = "decided"
    DECIDED_WON = "decided-won"
    CONCEDED = "conceded"
    SHORTENED = "shortened"
    REST_TO_OPPONENTS = "rest-to-opponents"


_REST_COUNTS_FOR_DECLARER: Final = frozenset(
    {Ending.OPPONENTS_THREW_DOWN, Ending.DECIDED, Ending.CONCEDED, Ending.SHORTENED}
)


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
    or for the declarer when the opponents threw down, the game ended decided against him, an opponent conceded it or he shortened it:
    then the opponents keep only the tricks and points they completed.
    `claimed` is the level the declarer demanded with his shortening; no other ending reads it.
    """

    declared: Declaring
    tricks: tuple[CompletedTrick, ...]
    ending: Ending = Ending.PLAYED_OUT
    claimed: Announcement = Announcement.NONE

    @property
    def tally(self) -> Tally:
        return _tally(self.declared.declarer, self.tricks)

    @property
    def _opponents_keep_only_their_completed_tricks(self) -> bool:
        return self.ending in _REST_COUNTS_FOR_DECLARER

    @property
    def _tricks_left(self) -> int:
        return TRICKS_IN_A_GAME - len(self.tricks)

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
class TenTricks:
    """The cards, the trick in progress and the tricks taken, whoever plays them; a game narrows the result."""

    hands: Mapping[Position, tuple[Card, ...]]
    leader: Position
    current: tuple[Card, ...]
    tricks: tuple[CompletedTrick, ...]
    result: object

    @property
    def turn(self) -> Position:
        return _position_after(self.leader, len(self.current))

    @property
    def current_plays(self) -> tuple[CardPlayed, ...]:
        """The cards of the trick in progress, each with the position that played it, in playing order."""
        return tuple(CardPlayed(_position_after(self.leader, place), card) for place, card in enumerate(self.current))


@dataclass(frozen=True)
class Playing(TenTricks):
    """The ten tricks in progress; the result is empty until the tenth trick is taken or the game ends early."""

    declared: Declaring
    result: PlayedOut | None

    @property
    def tally(self) -> Tally:
        return _tally(self.declared.declarer, self.tricks)


@dataclass(frozen=True)
class PlayOutcome[GameState: TenTricks = Playing]:
    """The state after a card; a refusal leaves it as it was."""

    state: GameState
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


def _refusal(state: TenTricks, position: Position, card: Card, kind: GameKind) -> PlayRefusal | None:
    if state.result is not None:
        return PlayRefusal.OVER
    if position is not state.turn:
        return PlayRefusal.NOT_YOUR_TURN
    hand = state.hands[position]
    if card not in hand:
        return PlayRefusal.NOT_IN_HAND
    first = state.current[0] if state.current else None
    if card not in legal_cards(hand, first, kind):
        return PlayRefusal.MUST_FOLLOW
    return None


def _complete_trick(leader: Position, cards: tuple[Card, Card, Card], kind: GameKind) -> CompletedTrick:
    return CompletedTrick(leader, cards, _position_after(leader, trick_winner(cards, kind)))


def _decides_the_game(declared: Declaring, trick: CompletedTrick) -> bool:
    """A Null game is decided by the declarer's first trick, a game announced Schwarz by the opponents' first."""
    taken_by_declarer = trick.taker is declared.declarer
    if _kind_of(declared) is GameKind.NULL:
        return taken_by_declarer
    return not taken_by_declarer and _declaration_of(declared).announcement is Announcement.SCHWARZ


def _game_result(state: Playing, tricks: tuple[CompletedTrick, ...]) -> PlayedOut | None:
    """The tenth trick ends every game; before it only the trick just completed can decide one."""
    if len(tricks) == TRICKS_IN_A_GAME:
        return PlayedOut(state.declared, tricks)
    if _decides_the_game(state.declared, tricks[-1]):
        return PlayedOut(state.declared, tricks, Ending.DECIDED)
    return None


def trick_step[GameState: TenTricks](
    state: GameState,
    position: Position,
    card: Card,
    kind: GameKind,
    result_of: Callable[[GameState, tuple[CompletedTrick, ...]], object],
) -> PlayOutcome[GameState]:
    """One card of the ten tricks; `result_of` is asked after every completed trick."""
    refusal = _refusal(state, position, card, kind)
    if refusal is not None:
        return PlayOutcome(state, refusal)
    hands = {**state.hands, position: tuple(each for each in state.hands[position] if each != card)}
    current = (*state.current, card)
    if len(current) < _TRICK_SIZE:
        return PlayOutcome(replace(state, hands=MappingProxyType(hands), current=current))
    trick = _complete_trick(state.leader, (current[0], current[1], current[2]), kind)
    tricks = (*state.tricks, trick)
    return PlayOutcome(
        replace(
            state,
            hands=MappingProxyType(hands),
            leader=trick.taker,
            current=(),
            tricks=tricks,
            result=result_of(state, tricks),
        )
    )


type _Hands = tuple[tuple[Card, ...], ...]
type _Key = tuple[tuple[int, ...], tuple[tuple[int, ...], ...], int]


class _NoFurtherTrickSearch:
    """Whether the shortener can keep the declarer from every further trick, whatever the other two play.

    The shortener picks a card at each of his turns, the other two answer with every legal card. A trick the declarer
    takes ends a line as false, a game the engine decides as true. Only the relative order of the cards in each playing
    suit decides a trick, so a position at a trick boundary is known by who owns the remaining cards of each suit in
    strength order and by the leader; the plain suits are interchangeable.
    """

    def __init__(self, declared: Declaring, shortener: Position) -> None:
        self._declared = declared
        self._kind = _kind_of(declared)
        self._shortener = _PLAY_ORDER.index(shortener)
        self._known: dict[_Key, bool] = {}

    def _key(self, hands: _Hands, leader: int) -> _Key:
        by_suit: dict[object, list[tuple[int, int]]] = {}
        for owner, hand in enumerate(hands):
            for card in hand:
                by_suit.setdefault(self._kind.playing_suit(card), []).append((self._kind.strength(card), owner))
        trumps = tuple(owner for _, owner in sorted(by_suit.pop(Trump.TRUMP, [])))
        plain = sorted(tuple(owner for _, owner in sorted(cards)) for cards in by_suit.values())
        return trumps, tuple(plain), leader

    def holds(self, hands: _Hands, leader: int, trick: tuple[Card, ...]) -> bool:
        at_boundary = not trick
        key = self._key(hands, leader) if at_boundary else None
        if key is not None and key in self._known:
            return self._known[key]
        turn = (leader + len(trick)) % len(_PLAY_ORDER)
        moves = legal_cards(hands[turn], trick[0] if trick else None, self._kind)
        answers = (self._after(hands, leader, trick, turn, card) for card in moves)
        answer = any(answers) if turn == self._shortener else all(answers)
        if key is not None:
            self._known[key] = answer
        return answer

    def _after(self, hands: _Hands, leader: int, trick: tuple[Card, ...], turn: int, card: Card) -> bool:
        remaining = (*hands[:turn], tuple(each for each in hands[turn] if each != card), *hands[turn + 1 :])
        played = (*trick, card)
        if len(played) < _TRICK_SIZE:
            return self.holds(remaining, leader, played)
        completed = _complete_trick(_PLAY_ORDER[leader], (played[0], played[1], played[2]), self._kind)
        if completed.taker is self._declared.declarer:
            return False
        if _decides_the_game(self._declared, completed) or not any(remaining):
            return True
        return self.holds(remaining, _PLAY_ORDER.index(completed.taker), ())


def declarer_takes_no_further_trick(state: Playing, shortener: Position) -> bool:
    """Whether `shortener` can play so that, against every legal play of the declarer and the other opponent, the
    declarer takes no further trick before the game ends; a trick in progress counts.

    It reads every hand: no table or view may call it, or it tells the hidden cards.
    """
    hands = tuple(state.hands[position] for position in _PLAY_ORDER)
    search = _NoFurtherTrickSearch(state.declared, shortener)
    return search.holds(hands, _PLAY_ORDER.index(state.leader), state.current)


def play_card(state: Playing, position: Position, card: Card) -> PlayOutcome:
    return trick_step(state, position, card, _kind_of(state.declared), _game_result)


def replay_cards[GameState: TenTricks](
    start: GameState,
    steps: tuple[CardPlayed, ...],
    play: Callable[[GameState, Position, Card], PlayOutcome[GameState]],
) -> GameState:
    """The state a stored log of cards leads to; a log the rules refuse raises."""
    return replay_log(start, steps, lambda state, step: play(state, step.position, step.card), "card")


def playing_after(start: Playing, steps: tuple[CardPlayed, ...]) -> Playing:
    return replay_cards(start, steps, play_card)
