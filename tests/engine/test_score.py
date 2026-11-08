import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal
from skat.engine.declaration import Announcement, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind
from skat.engine.score import Settlement, settle
from skat.engine.tricks import CompletedTrick, PlayedOut
from skat.engine.value import value_of
from tests.engine.test_value import (
    CLUBS_JACK,
    FOREHAND,
    HEARTS_JACK,
    HERZ,
    KARO,
    MIDDLEHAND,
    NULL,
    REARHAND,
    SPADES_JACK,
    WIN_SCHNEIDER,
    WIN,
    game,
    trick_worth,
)

LOST = (30, 20)  # 50 points
SEVENTY_POINTS = (30, 30, 10)


def played_with_twelve(
    twelve: tuple[Card, ...], kind: GameKind, declarer_tricks: tuple[int, ...], *, hand: bool = False
) -> PlayedOut:
    """Middlehand holds exactly these twelve cards (the last two are the skat) and declares the kind."""
    skat = twelve[10:]
    rest = iter(card for card in DECK if card not in twelve)
    the_deal = Deal(tuple(next(rest) for _ in range(10)), twelve[:10], tuple(next(rest) for _ in range(10)), skat)
    state = Declaring.start(Declared(MIDDLEHAND, 18), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, skat).state
    outcome = declare(state, kind, hand=hand, ouvert=False, announcement=Announcement.NONE)
    assert outcome.refusal is None
    tricks = tuple(CompletedTrick(FOREHAND, trick_worth(points), MIDDLEHAND) for points in declarer_tricks) + tuple(
        CompletedTrick(FOREHAND, trick_worth(0), REARHAND) for _ in range(10 - len(declarer_tricks))
    )
    return PlayedOut(outcome.state, tricks)


def test_a_game_won_by_play_below_the_bid_is_overbid_and_lost_at_the_base_multiplied_to_the_bid() -> None:
    played = game(KARO, (CLUBS_JACK,), SEVENTY_POINTS)
    assert value_of(played).won
    assert settle(played, 20) == Settlement(won=False, value=27, score=-54)


def test_a_level_reached_counts_in_the_comparison_with_the_bid() -> None:
    assert settle(game(KARO, (CLUBS_JACK,), WIN_SCHNEIDER), 20) == Settlement(won=True, value=27, score=27)


def test_a_game_lost_by_play_below_the_bid_is_valued_at_least_at_the_bid_too() -> None:
    assert settle(game(HERZ, (CLUBS_JACK,), LOST), 30) == Settlement(won=False, value=30, score=-60)


def test_a_hand_game_short_of_the_bid_because_a_top_trump_lay_in_the_skat_is_lost_with_over_60_points() -> None:
    plain = [card for card in DECK if card.rank not in (Rank.JACK, Rank.SEVEN)]
    twelve = (*plain[:10], CLUBS_JACK, Card(Suit.KARO, Rank.SEVEN))
    played = played_with_twelve(twelve, KARO, SEVENTY_POINTS, hand=True)
    assert played.declarer_points > 60
    assert settle(played, 54) == Settlement(won=False, value=54, score=-108)


def test_a_game_worth_exactly_the_bid_is_won() -> None:
    played = game(KARO, (CLUBS_JACK,), WIN_SCHNEIDER)
    assert settle(played, value_of(played).value) == Settlement(won=True, value=27, score=27)


def test_a_won_game_scores_its_value_and_a_lost_game_minus_twice_its_value_at_or_above_the_bid() -> None:
    jacks = (CLUBS_JACK, SPADES_JACK, HEARTS_JACK)  # Karo mit 3, Spiel: 4 x 9
    assert settle(game(KARO, jacks, WIN), 30) == Settlement(won=True, value=36, score=36)
    assert settle(game(KARO, jacks, LOST), 30) == Settlement(won=False, value=36, score=-72)


@pytest.mark.parametrize(
    ("hand", "ouvert", "declarer_tricks", "expected"),
    [
        (False, False, (), Settlement(won=True, value=23, score=23)),
        (False, False, (12,), Settlement(won=False, value=23, score=-46)),
        (True, True, (12,), Settlement(won=False, value=59, score=-118)),
    ],
)
def test_null_games_at_a_bid_they_reach_follow_the_same_score_rule(
    hand: bool, ouvert: bool, declarer_tricks: tuple[int, ...], expected: Settlement
) -> None:
    assert settle(game(NULL, hand=hand, ouvert=ouvert, declarer_tricks=declarer_tricks), 18) == expected


@pytest.mark.parametrize("declarer_tricks", [(), (12,)])
def test_a_null_below_the_bid_is_lost_as_the_cheapest_game_reaching_the_bid_with_the_matadors(
    declarer_tricks: tuple[int, ...],
) -> None:
    plain = [card for card in DECK if card.rank is not Rank.JACK]
    twelve = (CLUBS_JACK, SPADES_JACK, *plain[:10])
    played = played_with_twelve(twelve, NULL, declarer_tricks)
    assert settle(played, 30) == Settlement(won=False, value=30, score=-60)


def test_the_matadors_raise_the_loss_of_a_null_above_the_bid() -> None:
    twelve = tuple(card for card in DECK if card.rank in (Rank.KING, Rank.QUEEN, Rank.NINE))
    assert settle(played_with_twelve(twelve, NULL, ()), 24) == Settlement(won=False, value=63, score=-126)

