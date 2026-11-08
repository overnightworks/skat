from itertools import combinations_with_replacement

import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind, Trump
from skat.engine.score import Reckoning, Settlement, reckon, settle
from skat.engine.tricks import CompletedTrick, PlayedOut
from skat.engine.value import value_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KARO, HERZ, NULL = GameKind.KARO, GameKind.HERZ, GameKind.NULL
CLUBS_JACK, SPADES_JACK = Card(Suit.KREUZ, Rank.JACK), Card(Suit.PIK, Rank.JACK)
HEARTS_JACK = Card(Suit.HERZ, Rank.JACK)
CARD_POINTS = (0, 2, 3, 4, 10, 11)
RANKS_BY_POINTS = {0: Rank.SEVEN, 2: Rank.JACK, 3: Rank.QUEEN, 4: Rank.KING, 10: Rank.TEN, 11: Rank.ACE}
WIN = (30, 30, 20)  # 80 points, the opponents 40: no Schneider
WIN_SCHNEIDER = (30, 30, 30, 5)  # 95 points, the opponents 25
LOST = (30, 20)  # 50 points
SEVENTY_POINTS = (30, 30, 10)


def trick_worth(points: int) -> tuple[Card, Card, Card]:
    for combination in combinations_with_replacement(CARD_POINTS, 3):
        if sum(combination) == points:
            first, second, third = (Card(Suit.KARO, RANKS_BY_POINTS[each]) for each in combination)
            return first, second, third
    raise AssertionError(points)


def twelve_holding(kind: GameKind, trumps: tuple[Card, ...]) -> tuple[Card, ...]:
    """The chosen trumps, filled up with plain cards of no points in the skat."""
    plain = [card for card in DECK if kind.playing_suit(card) is not Trump.TRUMP and card not in trumps]
    skat = [card for card in plain if card.points == 0][:2]
    return (*trumps, *(card for card in plain if card not in skat))[:10] + tuple(skat)


def game(
    kind: GameKind,
    trumps: tuple[Card, ...] = (),
    declarer_tricks: tuple[int, ...] = (),
    *,
    hand: bool = False,
    ouvert: bool = False,
) -> PlayedOut:
    return played_with_twelve(twelve_holding(kind, trumps), kind, declarer_tricks, hand=hand, ouvert=ouvert)


def played_with_twelve(
    twelve: tuple[Card, ...],
    kind: GameKind,
    declarer_tricks: tuple[int, ...],
    *,
    hand: bool = False,
    ouvert: bool = False,
) -> PlayedOut:
    """Middlehand holds exactly these twelve cards (the last two are the skat) and declares the kind."""
    skat = twelve[10:]
    rest = iter(card for card in DECK if card not in twelve)
    the_deal = Deal(tuple(next(rest) for _ in range(10)), twelve[:10], tuple(next(rest) for _ in range(10)), skat)
    state = Declaring.start(Declared(MIDDLEHAND, 18), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, skat).state
    outcome = declare(state, kind, hand=hand, ouvert=ouvert, announcement=Announcement.NONE)
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


@pytest.mark.parametrize(
    ("settlement", "expected"),
    [
        (Settlement(won=True, value=36, score=36), Reckoning(declarer=86, each_opponent=0)),
        (Settlement(won=False, value=36, score=-72), Reckoning(declarer=-122, each_opponent=40)),
        (Settlement(won=False, value=23, score=-46), Reckoning(declarer=-96, each_opponent=40)),
    ],
)
def test_a_game_adds_to_the_declarer_and_each_opponent(settlement: Settlement, expected: Reckoning) -> None:
    assert reckon(settlement) == expected


def test_an_overbid_game_is_reckoned_as_a_lost_game() -> None:
    settlement = settle(game(KARO, (CLUBS_JACK,), SEVENTY_POINTS), 20)
    assert reckon(settlement) == Reckoning(declarer=-104, each_opponent=40)


def test_the_reckonings_of_three_declared_and_three_lost_by_the_others_sum_to_the_contract_total() -> None:
    own = [
        Settlement(won=True, value=60, score=60),
        Settlement(won=True, value=80, score=80),
        Settlement(won=False, value=20, score=-40),
    ]
    others_lost = Settlement(won=False, value=20, score=-40)
    total = sum(reckon(each).declarer for each in own) + 3 * reckon(others_lost).each_opponent
    assert total == 270
