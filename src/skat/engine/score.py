from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skat.engine.games import GameKind
from skat.engine.value import Valuation, matadors, value_of

if TYPE_CHECKING:
    from skat.engine.tricks import PlayedOut

_GAME_BONUS: Final = 50
_OPPONENT_SHARE_OF_A_LOST_GAME: Final = 40  # three-player table

_SUIT_AND_GRAND_GAMES: Final = tuple(kind for kind in GameKind if kind is not GameKind.NULL)


@dataclass(frozen=True)
class Settlement:
    """How a played game ends: whether it was won, at which value, and the score that follows."""

    won: bool
    value: int
    score: int


def _raised_to_reach(value: int, base: int, bid: int) -> int:
    """The value, or the smallest multiple of the base that reaches the bid when the value falls short."""
    return value if value >= bid else -(-bid // base) * base


def _cheapest_game_reaching(played: PlayedOut, bid: int) -> int:
    twelve = (*played.declared.hand, *played.declared.skat)
    values: list[int] = []
    for kind in _SUIT_AND_GRAND_GAMES:
        held = matadors(twelve, kind)
        base = kind.base_value
        assert held is not None  # noqa: S101 - narrows the type; only Null has no matadors
        assert base is not None  # noqa: S101 - narrows the type; only Null has no base value
        values.append(_raised_to_reach((held.count + 1) * base, base, bid))
    return min(values)


def _settled_value(valuation: Valuation, played: PlayedOut, bid: int) -> int:
    if valuation.value >= bid:
        return valuation.value
    if valuation.matadors is None:
        return _cheapest_game_reaching(played, bid)
    declaration = played.declared.declaration
    assert declaration is not None  # noqa: S101 - narrows the type; a played-out game is declared
    base = declaration.kind.base_value
    assert base is not None  # noqa: S101 - narrows the type; only Null has no base value
    return _raised_to_reach(valuation.value, base, bid)


def settle(played: PlayedOut, bid: int) -> Settlement:
    """A game valued below the bid is lost at least at the bid; a lost game scores minus twice its value."""
    valuation = value_of(played)
    value = _settled_value(valuation, played, bid)
    won = valuation.won and valuation.value >= bid
    return Settlement(won=won, value=value, score=value if won else -2 * value)


@dataclass(frozen=True)
class Reckoning:
    """What a played game adds to the declarer's total and to each opponent's."""

    declarer: int
    each_opponent: int


def reckon(settlement: Settlement) -> Reckoning:
    """A won game adds its score plus 50 to the declarer; a lost one its score minus 50, and 40 to each opponent."""
    if settlement.won:
        return Reckoning(declarer=settlement.score + _GAME_BONUS, each_opponent=0)
    return Reckoning(declarer=settlement.score - _GAME_BONUS, each_opponent=_OPPONENT_SHARE_OF_A_LOST_GAME)
