from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skat.engine.cards import DECK, Card

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping

SEATS: Final = (1, 2, 3)
_PACKETS: Final = (3, 2, 4, 3)


class Position(Enum):
    FOREHAND = "forehand"
    MIDDLEHAND = "middlehand"
    REARHAND = "rearhand"


@dataclass(frozen=True)
class Deal:
    forehand: tuple[Card, ...]
    middlehand: tuple[Card, ...]
    rearhand: tuple[Card, ...]
    skat: tuple[Card, ...]

    @property
    def hands(self) -> Mapping[Position, tuple[Card, ...]]:
        return MappingProxyType(
            {
                Position.FOREHAND: self.forehand,
                Position.MIDDLEHAND: self.middlehand,
                Position.REARHAND: self.rearhand,
            }
        )


def _check_seat(seat: int) -> None:
    if seat not in SEATS:
        raise ValueError(f"seat {seat} is not one of {SEATS}")


def next_dealer(dealer: int) -> int:
    _check_seat(dealer)
    return dealer % len(SEATS) + 1


def positions_from(dealer: int) -> dict[int, Position]:
    """Forehand sits left of the dealer, middlehand next, and the dealer is rearhand."""
    _check_seat(dealer)
    forehand = next_dealer(dealer)
    middlehand = next_dealer(forehand)
    return {
        forehand: Position.FOREHAND,
        middlehand: Position.MIDDLEHAND,
        dealer: Position.REARHAND,
    }


def deal(source: random.Random) -> Deal:
    """Shuffle the whole deck with `source`, then deal 3 each, 2 to the skat, 4 each, 3 each."""
    deck = list(DECK)
    source.shuffle(deck)
    players = list(Position)
    hands: dict[Position, list[Card]] = {position: [] for position in players}
    skat: list[Card] = []
    taken = 0
    for packet_index, size in enumerate(_PACKETS):
        if packet_index == 1:
            skat = deck[taken : taken + size]
            taken += size
            continue
        for position in players:
            hands[position] += deck[taken : taken + size]
            taken += size
    return Deal(
        forehand=tuple(hands[Position.FOREHAND]),
        middlehand=tuple(hands[Position.MIDDLEHAND]),
        rearhand=tuple(hands[Position.REARHAND]),
        skat=tuple(skat),
    )
