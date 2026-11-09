from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skat.engine.deal import Position
from skat.engine.games import GameKind
from skat.engine.tricks import (
    TRICKS_IN_A_GAME,
    CardPlayed,
    PlayOutcome,
    TenTricks,
    replay_cards,
    trick_step,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skat.engine.cards import Card
    from skat.engine.deal import Deal
    from skat.engine.tricks import CompletedTrick


@dataclass(frozen=True)
class RamschPlayedOut:
    """The finished Ramsch: each completed trick and the skat as it lay, which no player held."""

    tricks: tuple[CompletedTrick, ...]
    skat: tuple[Card, ...]

    def tricks_of(self, position: Position) -> int:
        return sum(trick.taker is position for trick in self.tricks)

    def points_of(self, position: Position) -> int:
        return sum(card.points for trick in self.tricks if trick.taker is position for card in trick.cards)

    @property
    def last_trick_taker(self) -> Position:
        return self.tricks[-1].taker


class RamschScoring(StrEnum):
    POINTS = "points"
    POINTS_BY_TEN = "points-by-ten"
    SKAT_TO_LOSER = "skat-to-loser"


class JungfrauRule(StrEnum):
    DOUBLES_LOSER = "doubles-loser"
    OFF = "off"


class DurchmarschRule(StrEnum):
    WINS_120 = "wins-120"
    WINS_120_FLAT = "wins-120-flat"
    OFF = "off"


@dataclass(frozen=True)
class RamschOptions:
    """How a table reckons a Ramsch: how points count, a player with no trick, all ten tricks."""

    scoring: RamschScoring
    jungfrau: JungfrauRule
    durchmarsch: DurchmarschRule


@dataclass(frozen=True)
class RamschReckoning:
    """Who pays what after a Ramsch; `gains` already carry the multiplier."""

    counted_points: Mapping[Position, int]
    losers: frozenset[Position]
    durchmarsch: Position | None
    jungfrau: bool
    gains: Mapping[Position, int]


_DURCHMARSCH_GAIN: Final = 120
_POINTS_PER_UNIT: Final = 10
_ALL_POSITIONS: Final = tuple(Position)


def _counted_points(played: RamschPlayedOut, scoring: RamschScoring) -> dict[Position, int]:
    skat_points = sum(card.points for card in played.skat)
    counted = {position: played.points_of(position) for position in _ALL_POSITIONS}
    if scoring is RamschScoring.SKAT_TO_LOSER:
        return {position: points + skat_points for position, points in counted.items()}
    counted[played.last_trick_taker] += skat_points
    return counted


def reckon_ramsch(played: RamschPlayedOut, options: RamschOptions, *, multiplier: int) -> RamschReckoning:
    """The Ramsch's gains per player; `multiplier` is the pushes and Bock as one number."""
    counted = _counted_points(played, options.scoring)
    sweeper = next((position for position in _ALL_POSITIONS if played.tricks_of(position) == TRICKS_IN_A_GAME), None)
    if sweeper is not None and options.durchmarsch is not DurchmarschRule.OFF:
        factor = 1 if options.durchmarsch is DurchmarschRule.WINS_120_FLAT else multiplier
        gains = dict.fromkeys(_ALL_POSITIONS, 0)
        gains[sweeper] = _DURCHMARSCH_GAIN * factor
        return RamschReckoning(counted, frozenset(), sweeper, jungfrau=False, gains=gains)
    most = max(counted.values())
    losers = frozenset(position for position, points in counted.items() if points == most)
    jungfrau = options.jungfrau is JungfrauRule.DOUBLES_LOSER and any(
        played.tricks_of(position) == 0 for position in _ALL_POSITIONS
    )
    payment = most // _POINTS_PER_UNIT if options.scoring is RamschScoring.POINTS_BY_TEN else most
    if jungfrau:
        payment *= 2
    gains = {position: -payment * multiplier if position in losers else 0 for position in _ALL_POSITIONS}
    return RamschReckoning(counted, losers, None, jungfrau=jungfrau, gains=gains)


@dataclass(frozen=True)
class RamschPlaying(TenTricks):
    """Three players each playing alone for ten tricks; the skat stays aside."""

    skat: tuple[Card, ...]
    result: RamschPlayedOut | None


def start_ramsch(cards: Deal) -> RamschPlaying:
    """A Ramsch from the four holdings as they lie, forehand to lead."""
    return RamschPlaying(
        hands=MappingProxyType(dict(cards.hands)),
        leader=Position.FOREHAND,
        current=(),
        tricks=(),
        result=None,
        skat=cards.skat,
    )


def _ramsch_result(state: RamschPlaying, tricks: tuple[CompletedTrick, ...]) -> RamschPlayedOut | None:
    if len(tricks) == TRICKS_IN_A_GAME:
        return RamschPlayedOut(tricks, state.skat)
    return None


def play_ramsch_card(state: RamschPlaying, position: Position, card: Card) -> PlayOutcome[RamschPlaying]:
    """A card in Grand's order, every player for himself."""
    return trick_step(state, position, card, GameKind.GRAND, _ramsch_result)


def ramsch_after(start: RamschPlaying, steps: tuple[CardPlayed, ...]) -> RamschPlaying:
    return replay_cards(start, steps, play_ramsch_card)
