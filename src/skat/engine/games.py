from dataclasses import dataclass
from enum import Enum
from typing import Final

from skat.engine.cards import Suit

HIGHEST_LEVEL: Final = 7  # Offen: the highest win level, counted after the matadors


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
