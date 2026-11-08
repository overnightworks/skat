import pytest

from skat.engine.cards import Suit
from skat.engine.games import HIGHEST_LEVEL, NULL_VALUES, GameKind, NullLevels


@pytest.mark.parametrize(
    ("kind", "base", "suit"),
    [
        (GameKind.KARO, 9, Suit.KARO),
        (GameKind.HERZ, 10, Suit.HERZ),
        (GameKind.PIK, 11, Suit.PIK),
        (GameKind.KREUZ, 12, Suit.KREUZ),
        (GameKind.GRAND, 24, None),
    ],
)
def test_suit_games_and_grand_have_their_base_values(kind: GameKind, base: int, suit: Suit | None) -> None:
    assert kind.base_value == base
    assert kind.suit == suit


def test_null_has_no_base_value() -> None:
    assert GameKind.NULL.base_value is None
    assert GameKind.NULL.highest_matadors is None
    assert GameKind.NULL.highest_faelle is None


@pytest.mark.parametrize(
    ("levels", "value"),
    [
        (NullLevels(hand=False, ouvert=False), 23),
        (NullLevels(hand=True, ouvert=False), 35),
        (NullLevels(hand=False, ouvert=True), 46),
        (NullLevels(hand=True, ouvert=True), 59),
    ],
)
def test_null_values_are_fixed(levels: NullLevels, value: int) -> None:
    assert NULL_VALUES[levels] == value


@pytest.mark.parametrize(
    ("kind", "matadors"),
    [(GameKind.KARO, 11), (GameKind.KREUZ, 11), (GameKind.GRAND, 4)],
)
def test_highest_faelle_is_the_highest_matador_count_plus_the_highest_level(kind: GameKind, matadors: int) -> None:
    assert kind.highest_matadors == matadors
    assert kind.highest_faelle == matadors + HIGHEST_LEVEL
