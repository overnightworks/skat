from itertools import combinations_with_replacement
from operator import attrgetter

import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaration, Declaring, declare, put_back, take_skat
from skat.engine.games import NULL_VALUES, GameKind, NullLevels, Trump
from skat.engine.tricks import CompletedTrick, PlayedOut
from skat.engine.value import Level, Matadors, levels_of, matadors, value_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KARO, HERZ, KREUZ, GRAND, NULL = GameKind.KARO, GameKind.HERZ, GameKind.KREUZ, GameKind.GRAND, GameKind.NULL
NONE, SCHNEIDER, SCHWARZ = Announcement.NONE, Announcement.SCHNEIDER, Announcement.SCHWARZ
CLUBS_JACK, SPADES_JACK = Card(Suit.KREUZ, Rank.JACK), Card(Suit.PIK, Rank.JACK)
HEARTS_JACK, DIAMONDS_JACK = Card(Suit.HERZ, Rank.JACK), Card(Suit.KARO, Rank.JACK)
JACKS = (CLUBS_JACK, SPADES_JACK, HEARTS_JACK, DIAMONDS_JACK)
ALL_TRUMPS = {
    kind: tuple(card for card in DECK if kind.playing_suit(card) is Trump.TRUMP) for kind in (KARO, HERZ, KREUZ, GRAND)
}
CARD_POINTS = (0, 2, 3, 4, 10, 11)
RANKS_BY_POINTS = {0: Rank.SEVEN, 2: Rank.JACK, 3: Rank.QUEEN, 4: Rank.KING, 10: Rank.TEN, 11: Rank.ACE}


def diamonds(*ranks: Rank) -> tuple[Card, ...]:
    return tuple(Card(Suit.KARO, rank) for rank in ranks)


def trick_worth(points: int) -> tuple[Card, Card, Card]:
    for combination in combinations_with_replacement(CARD_POINTS, 3):
        if sum(combination) == points:
            first, second, third = (Card(Suit.KARO, RANKS_BY_POINTS[each]) for each in combination)
            return first, second, third
    raise AssertionError(points)


def dealt_to_middlehand(kind: GameKind, trumps: tuple[Card, ...]) -> Deal:
    """The declarer holds the chosen trumps, filled up with plain cards; the skat holds no points if it can."""
    plain = [card for card in DECK if kind.playing_suit(card) is not Trump.TRUMP and card not in trumps]
    zero_points = [card for card in plain if card.points == 0]
    skat = tuple(zero_points[:2]) if len(trumps) <= 10 else (trumps[10], zero_points[0])
    pool = [card for card in (*trumps[:10], *plain) if card not in skat]
    hand = tuple(pool[:10])
    rest = iter(card for card in DECK if card not in {*hand, *skat})
    return Deal(tuple(next(rest) for _ in range(10)), hand, tuple(next(rest) for _ in range(10)), skat)


def game(
    kind: GameKind,
    trumps: tuple[Card, ...] = (),
    declarer_tricks: tuple[int, ...] = (),
    *,
    hand: bool = False,
    ouvert: bool = False,
    announcement: Announcement = NONE,
) -> PlayedOut:
    """The declarer (middlehand) takes tricks worth the given points; the opponents take the rest, worth none."""
    the_deal = dealt_to_middlehand(kind, trumps)
    state = Declaring.start(Declared(MIDDLEHAND, 18), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, the_deal.skat).state
    outcome = declare(state, kind, hand=hand, ouvert=ouvert, announcement=announcement)
    assert outcome.refusal is None
    tricks = tuple(CompletedTrick(FOREHAND, trick_worth(points), MIDDLEHAND) for points in declarer_tricks) + tuple(
        CompletedTrick(FOREHAND, trick_worth(0), REARHAND) for _ in range(10 - len(declarer_tricks))
    )
    return PlayedOut(outcome.state, tricks)


WIN = (30, 30, 20)  # 80 points, the opponents 40: no Schneider
WIN_SCHNEIDER = (30, 30, 30, 5)  # 95 points, the opponents 25
TAKES_ALL = (12,) * 10  # 120 points and every trick
LOSS_BY_ONE_TRICK = (13,) * 9  # 117 points, one trick short of every trick
DECLARER_ENDS_WITH_25 = (25,)  # 25 points: lost in Schneider
MIT_TWO = (CLUBS_JACK, SPADES_JACK)


@pytest.mark.parametrize(
    ("twelve", "kind", "expected"),
    [
        (MIT_TWO, KREUZ, Matadors(mit=True, count=2)),
        ((SPADES_JACK, HEARTS_JACK, DIAMONDS_JACK), KREUZ, Matadors(mit=False, count=1)),
        ((*JACKS, *diamonds(Rank.ACE, Rank.TEN)), KARO, Matadors(mit=True, count=6)),
        ((*JACKS, *diamonds(Rank.ACE, Rank.TEN, Rank.QUEEN)), KARO, Matadors(mit=True, count=6)),
        (diamonds(Rank.ACE), HERZ, Matadors(mit=False, count=11)),
        ((Card(Suit.HERZ, Rank.TEN),), HERZ, Matadors(mit=False, count=5)),
        ((CLUBS_JACK, SPADES_JACK, DIAMONDS_JACK), GRAND, Matadors(mit=True, count=2)),
        ((SPADES_JACK, HEARTS_JACK), GRAND, Matadors(mit=False, count=1)),
        ((), GRAND, Matadors(mit=False, count=4)),
    ],
)
def test_matadors_are_the_unbroken_run_of_top_trumps_the_declarer_holds_or_lacks(
    twelve: tuple[Card, ...], kind: GameKind, expected: Matadors
) -> None:
    assert matadors(twelve, kind) == expected


def test_the_run_continues_into_the_trump_suit_in_the_order_ace_ten_king_queen_nine_eight_seven() -> None:
    assert matadors((*JACKS, *diamonds(Rank.ACE, Rank.TEN)), KARO) == Matadors(mit=True, count=6)
    assert matadors(diamonds(Rank.TEN, Rank.KING), KARO) == Matadors(mit=False, count=5)


@pytest.mark.parametrize("kind", [KARO, HERZ, KREUZ, GRAND])
def test_the_full_run_of_trumps_is_the_highest_matador_count_of_its_kind(kind: GameKind) -> None:
    assert matadors(ALL_TRUMPS[kind], kind) == Matadors(mit=True, count=kind.highest_matadors)


@pytest.mark.parametrize("kind", [KARO, HERZ, KREUZ, GRAND])
def test_a_hand_holding_no_trump_at_all_is_ohne_every_trump_of_its_kind(kind: GameKind) -> None:
    assert matadors((), kind) == Matadors(mit=False, count=kind.highest_matadors)


def test_null_has_no_matadors() -> None:
    assert matadors(JACKS, NULL) is None


@pytest.mark.parametrize("trumps", [MIT_TWO, (HEARTS_JACK, DIAMONDS_JACK)])
def test_mit_and_ohne_count_the_same_number_of_faelle(trumps: tuple[Card, ...]) -> None:
    valuation = value_of(game(KREUZ, trumps, WIN))
    assert valuation.matadors is not None
    assert valuation.matadors.count == 2
    assert valuation.value == 36


def test_the_matadors_are_counted_over_the_dealt_ten_cards_plus_the_skat() -> None:
    played = game(KARO, ALL_TRUMPS[KARO], WIN)
    assert played.declared.skat[0] in ALL_TRUMPS[KARO]
    assert value_of(played).matadors == Matadors(mit=True, count=11)


@pytest.mark.parametrize(
    ("declarer_tricks", "value"),
    [(WIN, 36), (WIN_SCHNEIDER, 48), (TAKES_ALL, 60)],
)
def test_a_class_one_game_counts_spiel_one_schneider_two_and_schwarz_three_cumulatively(
    declarer_tricks: tuple[int, ...], value: int
) -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, declarer_tricks))
    assert valuation.won
    assert valuation.value == value


@pytest.mark.parametrize(
    ("declarer_tricks", "value"),
    [(WIN, 27), (WIN_SCHNEIDER, 36)],
)
def test_a_class_two_game_counts_hand_in_its_spiel_and_schneider_on_top(
    declarer_tricks: tuple[int, ...], value: int
) -> None:
    played = game(KARO, (CLUBS_JACK,), declarer_tricks, hand=True)
    assert value_of(played).value == value


def test_a_class_two_game_counts_an_unannounced_schwarz_as_level_four() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, TAKES_ALL, hand=True))
    assert valuation.value == 72


@pytest.mark.parametrize("won_play", [True, False])
@pytest.mark.parametrize(("hand", "ouvert"), [(False, False), (True, False), (False, True), (True, True)])
def test_a_null_game_has_its_fixed_value_and_no_matadors(hand: bool, ouvert: bool, won_play: bool) -> None:
    played = game(NULL, hand=hand, ouvert=ouvert, declarer_tricks=() if won_play else (12,))
    valuation = value_of(played)
    assert valuation.won is won_play
    assert valuation.matadors is None
    assert valuation.value == NULL_VALUES[NullLevels(hand=hand, ouvert=ouvert)]
    assert attrgetter("schneider", "schwarz")(valuation) == (False, False)


@pytest.mark.parametrize(
    ("hand", "ouvert", "value"),
    [(False, False, 23), (True, False, 35), (False, True, 46), (True, True, 59)],
)
def test_the_four_null_games_are_worth_23_35_46_and_59(hand: bool, ouvert: bool, value: int) -> None:
    assert value_of(game(NULL, hand=hand, ouvert=ouvert)).value == value


@pytest.mark.parametrize(
    ("declarer_tricks", "announcement", "levels"),
    [
        pytest.param(WIN, NONE, (False, False), id="neither"),
        pytest.param(WIN_SCHNEIDER, NONE, (True, False), id="opponents-schneider"),
        pytest.param(TAKES_ALL, NONE, (True, True), id="opponents-schwarz"),
        pytest.param(DECLARER_ENDS_WITH_25, NONE, (True, False), id="declarer-schneider"),
        pytest.param((), NONE, (True, True), id="declarer-schwarz"),
        pytest.param((30, 30, 15), SCHNEIDER, (True, False), id="schneider-announced-and-missed"),
        pytest.param((30, 30, 30, 11), SCHWARZ, (True, True), id="schwarz-announced-and-missed"),
    ],
)
def test_schneider_and_schwarz_name_the_levels_the_value_counts_whichever_side_suffered_them(
    declarer_tricks: tuple[int, ...], announcement: Announcement, levels: tuple[bool, bool]
) -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, declarer_tricks, hand=True, announcement=announcement))
    assert attrgetter("schneider", "schwarz")(valuation) == levels


def test_schneider_counts_for_a_lost_game_too() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, DECLARER_ENDS_WITH_25))
    assert not valuation.won
    assert valuation.value == 48


def test_schwarz_counts_for_a_lost_game_too() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, ()))
    assert not valuation.won
    assert valuation.value == 60


def test_a_hand_game_without_announcement_that_reaches_schwarz_counts_level_four_not_six() -> None:
    assert value_of(game(KREUZ, MIT_TWO, TAKES_ALL, hand=True)).value == 72


def test_a_missed_schneider_angesagt_is_lost_at_the_announced_level_and_not_counted_twice() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, (30, 30, 15), hand=True, announcement=SCHNEIDER))
    assert not valuation.won
    assert valuation.value == 72


def test_a_won_schneider_angesagt_game_counts_level_four() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, WIN_SCHNEIDER, hand=True, announcement=SCHNEIDER))
    assert valuation.won
    assert valuation.value == 72


def test_a_higher_level_than_announced_counts_the_higher_one() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, TAKES_ALL, hand=True, announcement=SCHNEIDER))
    assert valuation.won
    assert valuation.value == 84


def test_an_announced_schwarz_counts_every_step_up_to_level_six() -> None:
    valuation = value_of(game(GRAND, JACKS, TAKES_ALL, hand=True, announcement=SCHWARZ))
    assert valuation.won
    assert valuation.matadors == Matadors(mit=True, count=4)
    assert valuation.value == 240


def test_an_ouvert_game_lost_by_one_trick_counts_as_schwarz_angesagt_plus_ouvert() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, LOSS_BY_ONE_TRICK, hand=True, ouvert=True))
    assert not valuation.won
    assert valuation.value == 108


def test_an_ouvert_game_taking_every_trick_is_won_at_level_seven() -> None:
    valuation = value_of(game(KREUZ, MIT_TWO, TAKES_ALL, hand=True, ouvert=True))
    assert valuation.won
    assert valuation.value == 108


@pytest.mark.parametrize(("kind", "trumps"), [(KREUZ, ALL_TRUMPS[KREUZ]), (GRAND, ALL_TRUMPS[GRAND])])
def test_a_reached_ouvert_game_at_the_full_run_is_the_highest_level_and_the_most_faelle_of_its_kind(
    kind: GameKind, trumps: tuple[Card, ...]
) -> None:
    valuation = value_of(game(kind, trumps, TAKES_ALL, hand=True, ouvert=True))
    assert valuation.value == kind.base_value * kind.highest_faelle


def test_a_suit_game_won_by_play_but_missing_its_announced_schwarz_is_lost_at_the_announced_level() -> None:
    valuation = value_of(game(GRAND, JACKS, (30, 30, 30, 11), hand=True, announcement=SCHWARZ))
    assert not valuation.won
    assert valuation.value == 240


SPIEL, HAND_LEVEL = Level.SPIEL, Level.HAND
SCHNEIDER_LEVEL, SCHNEIDER_ANNOUNCED = Level.SCHNEIDER, Level.SCHNEIDER_ANNOUNCED
SCHWARZ_LEVEL, SCHWARZ_ANNOUNCED, OUVERT_LEVEL = Level.SCHWARZ, Level.SCHWARZ_ANNOUNCED, Level.OUVERT


@pytest.mark.parametrize(
    ("played", "levels"),
    [
        pytest.param(game(KREUZ, MIT_TWO, WIN), (SPIEL,), id="plain"),
        pytest.param(game(KREUZ, MIT_TWO, WIN, hand=True), (SPIEL, HAND_LEVEL), id="hand"),
        pytest.param(game(KREUZ, MIT_TWO, WIN_SCHNEIDER), (SPIEL, SCHNEIDER_LEVEL), id="schneider-reached"),
        pytest.param(
            game(KREUZ, MIT_TWO, TAKES_ALL), (SPIEL, SCHNEIDER_LEVEL, SCHWARZ_LEVEL), id="schwarz-unannounced"
        ),
        pytest.param(
            game(KREUZ, MIT_TWO, WIN_SCHNEIDER, hand=True, announcement=SCHNEIDER),
            (SPIEL, HAND_LEVEL, SCHNEIDER_LEVEL, SCHNEIDER_ANNOUNCED),
            id="schneider-announced-and-reached",
        ),
        pytest.param(
            game(KREUZ, MIT_TWO, (30, 30, 15), hand=True, announcement=SCHNEIDER),
            (SPIEL, HAND_LEVEL, SCHNEIDER_LEVEL, SCHNEIDER_ANNOUNCED),
            id="schneider-announced-and-missed",
        ),
        pytest.param(
            game(GRAND, JACKS, TAKES_ALL, hand=True, ouvert=True),
            (
                SPIEL,
                HAND_LEVEL,
                SCHNEIDER_LEVEL,
                SCHNEIDER_ANNOUNCED,
                SCHWARZ_LEVEL,
                SCHWARZ_ANNOUNCED,
                OUVERT_LEVEL,
            ),
            id="ouvert",
        ),
    ],
)
def test_the_levels_a_game_counts_come_in_the_order_of_the_rules(played: PlayedOut, levels: tuple[Level, ...]) -> None:
    declaration = played.declared.declaration
    assert declaration is not None
    valuation = value_of(played)
    assert levels_of(declaration, schneider=valuation.schneider, schwarz=valuation.schwarz) == levels


def test_a_null_game_counts_no_levels() -> None:
    declaration = Declaration(NULL, hand=False, ouvert=False, announcement=NONE)
    assert levels_of(declaration, schneider=False, schwarz=False) == ()
