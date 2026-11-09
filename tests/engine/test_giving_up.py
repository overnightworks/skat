import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind
from skat.engine.giving_up import give_up
from skat.engine.score import Reckoning, Settlement, reckon, settle
from skat.engine.tricks import Ending, PlayedOut, Playing, PlayRefusal, play_card, start_play

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KARO, KREUZ, HERZ, GRAND, NULL = GameKind.KARO, GameKind.KREUZ, GameKind.HERZ, GameKind.GRAND, GameKind.NULL
CLUBS_JACK, SPADES_JACK = Card(Suit.KREUZ, Rank.JACK), Card(Suit.PIK, Rank.JACK)
HEARTS_JACK = Card(Suit.HERZ, Rank.JACK)
JACKS = (CLUBS_JACK, SPADES_JACK, HEARTS_JACK)
KARO_ACE, KARO_TEN, KARO_SEVEN, KARO_EIGHT = (
    Card(Suit.KARO, rank) for rank in (Rank.ACE, Rank.TEN, Rank.SEVEN, Rank.EIGHT)
)


def dealt(forehand: tuple[Card, ...], middlehand: tuple[Card, ...], rearhand: tuple[Card, ...]) -> Deal:
    """A deal holding the chosen cards first in each hand, the rest filled in deck order."""
    chosen = {*forehand, *middlehand, *rearhand}
    rest = iter(card for card in DECK if card not in chosen)
    hands = [(*prefix, *(next(rest) for _ in range(10 - len(prefix)))) for prefix in (forehand, middlehand, rearhand)]
    return Deal(*hands, tuple(next(rest) for _ in range(2)))


def started(
    kind: GameKind = KARO,
    bid: int = 20,
    *,
    jacks: tuple[Card, ...] = (CLUBS_JACK,),
    hand: bool = False,
    ouvert: bool = False,
    announcement: Announcement = Announcement.NONE,
    cards: tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]] = ((), (), ()),
) -> Playing:
    """The forehand declares; he holds exactly `jacks` of the jacks, middlehand holds the others."""
    forehand, middlehand, rearhand = cards
    the_deal = dealt((*jacks, *forehand), (*(jack for jack in JACKS if jack not in jacks), *middlehand), rearhand)
    state = Declaring.start(Declared(FOREHAND, bid), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, the_deal.skat).state
    outcome = declare(state, kind, hand=hand, ouvert=ouvert, announcement=announcement)
    assert outcome.refusal is None
    return start_play(outcome.state, the_deal)


def ok(state: Playing, position: Position, card: Card) -> Playing:
    outcome = play_card(state, position, card)
    assert outcome.refusal is None
    return outcome.state


def next_card(state: Playing) -> Playing:
    """The player on turn plays the first card of its hand that is accepted."""
    position = state.turn
    return next(
        outcome.state for card in state.hands[position] if (outcome := play_card(state, position, card)).refusal is None
    )


def after_first_trick(*, declarer_takes: bool) -> Playing:
    """Karo mit 1; the first trick goes to the declarer's ace (21 points) or to middlehand's ace."""
    own_ace = (KARO_ACE,) if declarer_takes else ()
    state = started(cards=((*own_ace, KARO_SEVEN), (KARO_TEN, KARO_EIGHT) if declarer_takes else (KARO_ACE,), ()))
    lead = KARO_ACE if declarer_takes else KARO_SEVEN
    state = ok(state, FOREHAND, lead)
    state = ok(state, MIDDLEHAND, KARO_TEN if declarer_takes else KARO_ACE)
    return next_card(state)


def given_up(state: Playing) -> PlayedOut:
    outcome = give_up(state)
    assert outcome.refusal is None
    assert outcome.state.result is not None
    return outcome.state.result


def test_karo_mit_1_bid_20_given_up_before_the_first_card_is_lost_at_27() -> None:
    result = given_up(started())
    assert settle(result, 20) == Settlement(won=False, value=27, score=-54)


def test_the_declarer_can_give_up_after_the_first_trick_while_holding_nine_cards() -> None:
    state = after_first_trick(declarer_takes=True)
    assert len(state.hands[FOREHAND]) == 9
    assert settle(given_up(state), 20) == Settlement(won=False, value=27, score=-54)


def test_the_declarer_can_give_up_in_the_second_trick_before_his_own_card() -> None:
    state = after_first_trick(declarer_takes=False)
    while state.turn is not FOREHAND:
        state = next_card(state)
    assert (len(state.hands[FOREHAND]), len(state.current)) == (9, 2)
    assert settle(given_up(state), 20) == Settlement(won=False, value=27, score=-54)


def test_after_the_declarer_played_his_card_to_the_second_trick_giving_up_is_refused_and_play_goes_on() -> None:
    state = after_first_trick(declarer_takes=False)
    while len(state.hands[FOREHAND]) == 9:
        state = next_card(state)
    assert len(state.hands[FOREHAND]) == 8
    outcome = give_up(state)
    assert outcome.refusal is PlayRefusal.TOO_LATE_TO_GIVE_UP
    assert outcome.state == state
    assert next_card(state).result is None


def test_a_bid_of_30_overbid_after_pick_up_is_given_up_at_once_as_lost_at_30() -> None:
    result = given_up(started(HERZ, 30))
    assert settle(result, 30) == Settlement(won=False, value=30, score=-60)


@pytest.mark.parametrize(
    ("kind", "jacks", "bid", "declaration", "score"),
    [
        pytest.param(KREUZ, JACKS[:2], 18, {"hand": True}, -96, id="hand counts: (2 + 2) * 12"),
        pytest.param(
            KREUZ,
            JACKS[:2],
            18,
            {"hand": True, "announcement": Announcement.SCHNEIDER},
            -144,
            id="announced schneider counts: (2 + 4) * 12",
        ),
        pytest.param(
            GRAND,
            JACKS[:2],
            18,
            {"hand": True, "ouvert": True, "announcement": Announcement.SCHWARZ},
            -432,
            id="ouvert counts all seven levels: (2 + 7) * 24",
        ),
        pytest.param(NULL, (), 23, {}, -46, id="null"),
        pytest.param(NULL, (), 59, {"hand": True, "ouvert": True}, -118, id="null ouvert hand"),
        pytest.param(NULL, JACKS[:1], 27, {}, -54, id="overbid null costs the cheapest game reaching the bid"),
    ],
)
def test_a_given_up_game_is_valued_by_its_declared_levels_and_lost(
    kind: GameKind, jacks: tuple[Card, ...], bid: int, declaration: dict[str, object], score: int
) -> None:
    result = given_up(started(kind, bid, jacks=jacks, **declaration))  # type: ignore[arg-type]
    settlement = settle(result, bid)
    assert settlement == Settlement(won=False, value=-score // 2, score=score)


def test_schneider_is_not_counted_for_a_declarer_holding_21_points_who_gives_up() -> None:
    state = after_first_trick(declarer_takes=True)
    assert settle(given_up(state), 18) == Settlement(won=False, value=18, score=-36)


def test_a_lost_given_up_game_gives_the_declarer_minus_50_and_each_opponent_40() -> None:
    settlement = settle(given_up(started()), 20)
    assert reckon(settlement) == Reckoning(declarer=-54 - 50, each_opponent=40)


def test_a_game_already_given_up_or_played_out_refuses_giving_up_and_any_card_as_over() -> None:
    over = give_up(started()).state
    played_out = started()
    while played_out.result is None:
        played_out = next_card(played_out)
    for state in (over, played_out):
        assert give_up(state).refusal is PlayRefusal.OVER
        assert give_up(state).state == state
    assert play_card(over, FOREHAND, over.hands[FOREHAND][0]).refusal is PlayRefusal.OVER


def test_a_given_up_result_keeps_the_tricks_taken_so_far_and_a_played_out_one_is_played_out() -> None:
    state = after_first_trick(declarer_takes=True)
    result = given_up(state)
    assert (result.ending, result.tricks, result.won_by_play) == (Ending.GIVEN_UP, state.tricks, False)
    assert len(state.tricks) == 1
    played_out = started()
    while played_out.result is None:
        played_out = next_card(played_out)
    assert played_out.result.ending is Ending.PLAYED_OUT
