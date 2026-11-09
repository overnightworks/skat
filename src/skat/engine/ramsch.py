from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

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
