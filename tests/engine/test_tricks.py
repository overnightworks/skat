import random
from itertools import combinations_with_replacement

import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position, deal
from skat.engine.declaration import (
    Announcement,
    Declaring,
    declare,
    put_back,
    take_skat,
)
from skat.engine.games import GameKind
from skat.engine.tricks import CompletedTrick, PlayedOut, Playing, PlayOutcome, PlayRefusal, play_card, start_play

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
HERZ, GRAND, NULL = GameKind.HERZ, GameKind.GRAND, GameKind.NULL
BID = 30
OVER, NOT_YOUR_TURN = PlayRefusal.OVER, PlayRefusal.NOT_YOUR_TURN
NOT_IN_HAND, MUST_FOLLOW = PlayRefusal.NOT_IN_HAND, PlayRefusal.MUST_FOLLOW
DECLARER_TAKES, OPPONENTS_TAKE = True, False
KARO_SEVEN, KARO_EIGHT, KARO_ACE = Card(Suit.KARO, Rank.SEVEN), Card(Suit.KARO, Rank.EIGHT), Card(Suit.KARO, Rank.ACE)
KARO_TEN, PIK_ACE = Card(Suit.KARO, Rank.TEN), Card(Suit.PIK, Rank.ACE)
HERZ_ACE, HERZ_QUEEN = Card(Suit.HERZ, Rank.ACE), Card(Suit.HERZ, Rank.QUEEN)
CARD_POINTS = (0, 2, 3, 4, 10, 11)
ZERO_CARD, JACK_CARD = KARO_SEVEN, Card(Suit.KARO, Rank.JACK)


def dealt(
    forehand: tuple[Card, ...] = (),
    middlehand: tuple[Card, ...] = (),
    rearhand: tuple[Card, ...] = (),
    skat: tuple[Card, ...] = (),
) -> Deal:
    """A deal holding the chosen cards first in each hand, the rest filled in deck order."""
    chosen = {*forehand, *middlehand, *rearhand, *skat}
    rest = iter(card for card in DECK if card not in chosen)
    sizes = (10, 10, 10, 2)
    filled = [
        (*prefix, *(next(rest) for _ in range(size - len(prefix))))
        for prefix, size in zip((forehand, middlehand, rearhand, skat), sizes, strict=True)
    ]
    return Deal(*filled)


def declared_by(
    the_deal: Deal, declarer: Position = FOREHAND, kind: GameKind = GRAND, *, pick_up: tuple[Card, ...] = ()
) -> Declaring:
    state = Declaring.start(Declared(declarer, BID), the_deal)
    if pick_up:
        state = put_back(take_skat(state).state, pick_up).state
    outcome = declare(state, kind, hand=not pick_up, ouvert=False, announcement=Announcement.NONE)
    assert outcome.refusal is None
    return outcome.state


def started(the_deal: Deal | None = None, declarer: Position = FOREHAND, kind: GameKind = GRAND) -> Playing:
    the_deal = the_deal or dealt(forehand=(KARO_SEVEN,), middlehand=(KARO_ACE, PIK_ACE), rearhand=(KARO_EIGHT,))
    return start_play(declared_by(the_deal, declarer, kind), the_deal)


def ok(outcome: PlayOutcome) -> Playing:
    assert outcome.refusal is None
    return outcome.state


def refused(outcome: PlayOutcome, reason: PlayRefusal, before: Playing) -> None:
    assert outcome.refusal is reason
    assert outcome.state == before


def first_trick_taken_by_middlehand() -> Playing:
    state = ok(play_card(started(), FOREHAND, KARO_SEVEN))
    state = ok(play_card(state, MIDDLEHAND, KARO_ACE))
    return ok(play_card(state, REARHAND, KARO_EIGHT))


def play_out(state: Playing) -> Playing:
    """Every player in turn plays the first card of its hand that is accepted."""
    while state.result is None:
        position = state.turn
        accepted = [
            outcome.state
            for card in state.hands[position]
            if (outcome := play_card(state, position, card)).refusal is None
        ]
        state = accepted[0]
    return state


def played_out_game(seed: int, kind: GameKind) -> Playing:
    the_deal = deal(random.Random(seed))
    declarer = list(Position)[seed % 3]
    return play_out(start_play(declared_by(the_deal, declarer, kind), the_deal))


def declarer_trick_points(state: Playing) -> int:
    assert state.result is not None
    declarer = state.result.declared.declarer
    return sum(card.points for trick in state.result.tricks if trick.taker is declarer for card in trick.cards)


def cards_worth(points: int, size: int = 3) -> tuple[Card, ...]:
    suits = iter(Suit)
    for combination in combinations_with_replacement(CARD_POINTS, size):
        if sum(combination) == points:
            ranks = {0: Rank.SEVEN, 2: Rank.JACK, 3: Rank.QUEEN, 4: Rank.KING, 10: Rank.TEN, 11: Rank.ACE}
            return tuple(Card(next(suits, Suit.KARO), ranks[each]) for each in combination)
    raise AssertionError(points)


def played_out(takes: tuple[tuple[bool, int], ...], kind: GameKind = HERZ, skat_points: int = 0) -> PlayedOut:
    """Ten chosen tricks of the declarer (middlehand) and the opponents, each worth the given points."""
    the_deal = dealt(skat=cards_worth(skat_points, 2))
    declared = declared_by(the_deal, MIDDLEHAND, kind)
    tricks = tuple(
        CompletedTrick(
            leader=FOREHAND,
            cards=cards_worth(points),
            taker=MIDDLEHAND if by_declarer else REARHAND,
        )
        for by_declarer, points in takes
    )
    return PlayedOut(declared, tricks)


def takes(declarer: tuple[int, ...], opponents: tuple[int, ...] = ()) -> tuple[tuple[bool, int], ...]:
    """The declarer's tricks, then the opponents'; zero-point opponent tricks fill the ten."""
    filler = (0,) * (10 - len(declarer) - len(opponents))
    return tuple((DECLARER_TAKES, points) for points in declarer) + tuple(
        (OPPONENTS_TAKE, points) for points in (*opponents, *filler)
    )


def test_forehand_leads_the_first_trick_and_the_declarer_holds_the_declared_ten_cards() -> None:
    the_deal = dealt()
    declared = declared_by(the_deal, MIDDLEHAND, GRAND)
    state = start_play(declared, the_deal)
    assert state.turn is FOREHAND
    assert state.hands[MIDDLEHAND] == declared.hand
    assert state.hands[FOREHAND] == the_deal.forehand
    assert state.hands[REARHAND] == the_deal.rearhand


def test_a_card_before_forehand_has_led_is_refused_as_not_your_turn() -> None:
    state = started()
    refused(play_card(state, MIDDLEHAND, KARO_ACE), NOT_YOUR_TURN, state)


def test_a_card_the_position_does_not_hold_is_refused_as_not_in_hand() -> None:
    state = started()
    refused(play_card(state, FOREHAND, PIK_ACE), NOT_IN_HAND, state)


def test_a_card_that_does_not_follow_the_suit_led_is_refused_as_must_follow() -> None:
    state = ok(play_card(started(), FOREHAND, KARO_SEVEN))
    refused(play_card(state, MIDDLEHAND, PIK_ACE), MUST_FOLLOW, state)


def test_the_taker_of_a_trick_leads_the_next_one() -> None:
    state = first_trick_taken_by_middlehand()
    assert state.tricks[0].taker is MIDDLEHAND
    assert state.leader is MIDDLEHAND
    refused(play_card(state, FOREHAND, state.hands[FOREHAND][0]), NOT_YOUR_TURN, state)
    assert play_card(state, MIDDLEHAND, PIK_ACE).refusal is None


@pytest.mark.parametrize("kind", [HERZ, GRAND, NULL])
@pytest.mark.parametrize("seed", range(5))
def test_a_game_is_ten_tricks_of_three_cards_and_leaves_every_hand_empty(seed: int, kind: GameKind) -> None:
    state = played_out_game(seed, kind)
    assert state.result is not None
    assert all(hand == () for hand in state.hands.values())
    assert len(state.result.tricks) == 10
    assert all(len(trick.cards) == 3 for trick in state.result.tricks)
    assert len({card for trick in state.result.tricks for card in trick.cards}) == 30


def test_any_card_after_the_tenth_trick_is_refused_as_over() -> None:
    state = played_out_game(1, HERZ)
    refused(play_card(state, FOREHAND, KARO_SEVEN), OVER, state)


@pytest.mark.parametrize("kind", [HERZ, GRAND, NULL])
@pytest.mark.parametrize("seed", range(20))
def test_the_two_sides_add_up_to_120_points_and_ten_tricks(seed: int, kind: GameKind) -> None:
    result = played_out_game(seed, kind).result
    assert result is not None
    assert result.declarer_points + result.opponents_points == 120
    assert result.declarer_tricks + result.opponents_tricks == 10


def test_a_skat_put_back_after_pick_up_counts_for_the_declarer() -> None:
    the_deal = dealt(forehand=(HERZ_ACE, HERZ_QUEEN))
    declared = declared_by(the_deal, FOREHAND, HERZ, pick_up=(HERZ_ACE, HERZ_QUEEN))
    state = play_out(start_play(declared, the_deal))
    assert state.result is not None
    assert state.result.declarer_points == declarer_trick_points(state) + 14


def test_an_untouched_skat_in_a_hand_game_counts_for_the_declarer() -> None:
    the_deal = dealt(skat=(KARO_ACE, KARO_TEN))
    state = play_out(start_play(declared_by(the_deal, FOREHAND, HERZ), the_deal))
    assert state.result is not None
    assert state.result.declarer_points == declarer_trick_points(state) + 21


@pytest.mark.parametrize(("trick_points", "won"), [((22, 22, 13), True), ((22, 22, 12), False)])
def test_a_suit_game_is_won_by_play_with_61_points_the_skat_included(trick_points: tuple[int, ...], won: bool) -> None:
    assert played_out(takes(trick_points), HERZ, skat_points=4).won_by_play is won


@pytest.mark.parametrize(
    ("declarer_tricks", "skat_points", "declarer_schneider", "opponents_schneider"),
    [
        ((22, 22, 22, 22), 2, False, True),
        ((22, 22, 22, 21), 2, False, False),
        ((22, 8), 0, True, False),
        ((22, 9), 0, False, False),
    ],
)
def test_a_side_with_30_points_or_fewer_is_schneider(
    declarer_tricks: tuple[int, ...], skat_points: int, declarer_schneider: bool, opponents_schneider: bool
) -> None:
    result = played_out(takes(declarer_tricks), HERZ, skat_points)
    assert result.declarer_schneider is declarer_schneider
    assert result.opponents_schneider is opponents_schneider


@pytest.mark.parametrize(
    ("chosen", "declarer_schwarz", "opponents_schwarz", "opponents_schneider"),
    [
        (takes((11,) * 10), False, True, True),
        (takes((11,) * 9, (0,)), False, False, True),
        (takes(()), True, False, False),
    ],
)
def test_a_side_is_schwarz_when_it_took_no_trick_however_few_points_it_holds(
    chosen: tuple[tuple[bool, int], ...], declarer_schwarz: bool, opponents_schwarz: bool, opponents_schneider: bool
) -> None:
    result = played_out(chosen)
    assert result.declarer_schwarz is declarer_schwarz
    assert result.opponents_schwarz is opponents_schwarz
    assert result.opponents_schneider is opponents_schneider


@pytest.mark.parametrize(
    ("chosen", "won"),
    [
        (tuple((OPPONENTS_TAKE, 0) if index != 3 else (DECLARER_TAKES, 0) for index in range(10)), False),
        (takes(()), True),
    ],
)
def test_a_null_game_is_won_by_play_only_if_the_declarer_takes_no_trick(
    chosen: tuple[tuple[bool, int], ...], won: bool
) -> None:
    result = played_out(chosen, NULL)
    assert len(result.tricks) == 10
    assert result.won_by_play is won


def test_over_is_refused_before_not_your_turn_and_not_your_turn_before_not_in_hand() -> None:
    finished = played_out_game(2, HERZ)
    refused(play_card(finished, REARHAND, KARO_SEVEN), OVER, finished)
    running = started()
    foreign = running.hands[REARHAND][0]
    refused(play_card(running, MIDDLEHAND, foreign), NOT_YOUR_TURN, running)


def test_starting_play_before_the_declaration_is_an_error() -> None:
    the_deal = dealt()
    with pytest.raises(ValueError, match="declaration"):
        start_play(Declaring.start(Declared(FOREHAND, BID), the_deal), the_deal)
