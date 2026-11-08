from dataclasses import dataclass
from enum import IntEnum
from typing import Final


class Suit(IntEnum):
    """The suits; a higher value ranks higher, so Kreuz ranks first."""

    KARO = 1
    HERZ = 2
    PIK = 3
    KREUZ = 4


class Rank(IntEnum):
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


_POINTS: Final = {
    Rank.ACE: 11,
    Rank.TEN: 10,
    Rank.KING: 4,
    Rank.QUEEN: 3,
    Rank.JACK: 2,
}


@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: Rank

    @property
    def points(self) -> int:
        return _POINTS.get(self.rank, 0)


DECK: Final = tuple(Card(suit, rank) for suit in reversed(Suit) for rank in Rank)
