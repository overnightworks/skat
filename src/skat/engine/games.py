from dataclasses import dataclass
from enum import Enum
from typing import Final

from skat.engine.cards import Card, Rank, Suit

HIGHEST_LEVEL: Final = 7  # Offen: the highest win level, counted after the matadors


class Trump(Enum):
    """The trump suit as a playing suit."""

    TRUMP = "trump"


_SUIT_ORDER: Final = (Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.QUEEN, Rank.KING, Rank.TEN, Rank.ACE)


@dataclass(frozen=True)
class _Kind:
    suit: Suit | None
    base_value: int | None
    highest_matadors: int | None


class GameKind(Enum):
    KARO = _Kind(Suit.KARO, 9, 11)
    HERZ = _Kind(Suit.HERZ, 10, 11)
    PIK = _Kind(Suit.PIK, 11, 11)
    KREUZ = _Kind(Suit.KREUZ, 12, 11)
    GRAND = _Kind(None, 24, 4)
    NULL = _Kind(None, None, None)

    @property
    def suit(self) -> Suit | None:
        return self.value.suit

    @property
    def base_value(self) -> int | None:
        return self.value.base_value

    @property
    def highest_matadors(self) -> int | None:
        return self.value.highest_matadors

    def playing_suit(self, card: Card) -> Suit | Trump:
        """The suit a card counts as in play: a jack is trump unless the game is Null."""
        if self is GameKind.NULL:
            return card.suit
        if card.rank is Rank.JACK or card.suit == self.suit:
            return Trump.TRUMP
        return card.suit

    def strength(self, card: Card) -> int:
        """The card's rank among the cards of its playing suit; higher beats lower."""
        if self is GameKind.NULL:
            return card.rank
        if card.rank is Rank.JACK:
            return len(_SUIT_ORDER) + card.suit
        return _SUIT_ORDER.index(card.rank)

    @property
    def highest_faelle(self) -> int | None:
        """The most fälle this kind can win: its highest matador count plus the highest level."""
        matadors = self.highest_matadors
        return None if matadors is None else matadors + HIGHEST_LEVEL


@dataclass(frozen=True)
class NullLevels:
    hand: bool
    ouvert: bool


NULL_VALUES: Final = {
    NullLevels(hand=False, ouvert=False): 23,
    NullLevels(hand=True, ouvert=False): 35,
    NullLevels(hand=False, ouvert=True): 46,
    NullLevels(hand=True, ouvert=True): 59,
}
