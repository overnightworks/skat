import pytest

from skat.engine.bidding import LOWEST_BID, Declared
from skat.engine.cards import Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaring, declare
from skat.engine.games import GameKind
from skat.engine.schieberamsch import (
    DeclareGrandHand,
    GrandHandRule,
    Push,
    Pushing,
    PushingRule,
    PushOptions,
    PushRefusal,
    PushStep,
    Put,
    RamschOn,
    Take,
    push_factor,
    pushing_after,
    pushing_step,
)
from skat.engine.score import Reckoning, Settlement, reckon, settle
from skat.engine.tricks import CompletedTrick, PlayedOut, start_play

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
STAY, JACKS_MAY_GO, NO_DOUBLING = PushingRule.JACKS_STAY, PushingRule.JACKS_MAY_GO, PushingRule.NO_DOUBLING
ALLOWED, OFF = GrandHandRule.ALLOWED, GrandHandRule.OFF
OVER, NOT_YOUR_TURN, OUT_OF_ORDER = PushRefusal.OVER, PushRefusal.NOT_YOUR_TURN, PushRefusal.OUT_OF_ORDER
GRAND_HAND_OFF, NOT_TWO, JACK_PUT_BACK = (
    PushRefusal.GRAND_HAND_OFF,
    PushRefusal.NOT_TWO_OF_THE_TWELVE,
    PushRefusal.JACK_PUT_BACK,
)

# Each hand holds two plain cards and one jack; the skat holds two plain cards.
FOREHAND_PLAIN = (Card(Suit.KREUZ, Rank.SEVEN), Card(Suit.KREUZ, Rank.EIGHT))
MIDDLEHAND_PLAIN = (Card(Suit.PIK, Rank.NINE), Card(Suit.PIK, Rank.TEN))
REARHAND_PLAIN = (Card(Suit.KARO, Rank.SEVEN), Card(Suit.KARO, Rank.EIGHT))
SKAT_CARDS = (Card(Suit.KARO, Rank.KING), Card(Suit.KARO, Rank.ACE))
CLUBS_JACK = Card(Suit.KREUZ, Rank.JACK)
DEAL = Deal(
    (*FOREHAND_PLAIN, CLUBS_JACK, Card(Suit.PIK, Rank.SEVEN), Card(Suit.PIK, Rank.EIGHT)),
    (*MIDDLEHAND_PLAIN, Card(Suit.PIK, Rank.JACK), Card(Suit.HERZ, Rank.SEVEN)),
    (*REARHAND_PLAIN, Card(Suit.HERZ, Rank.JACK), Card(Suit.HERZ, Rank.EIGHT)),
    SKAT_CARDS,
)
OPTIONS = PushOptions(pushing=STAY, grand_hand=ALLOWED)

PUSH_ALL = (Push(FOREHAND), Push(MIDDLEHAND), Push(REARHAND))


def options_of(pushing: PushingRule = STAY, grand_hand: GrandHandRule = ALLOWED) -> PushOptions:
    return PushOptions(pushing=pushing, grand_hand=grand_hand)


def played(steps: tuple[PushStep, ...], options: PushOptions = OPTIONS) -> Pushing:
    return pushing_after(Pushing.start(DEAL), steps, options)


def refused_by(steps: tuple[PushStep, ...], options: PushOptions = OPTIONS) -> PushRefusal | None:
    """The refusal of the last step; every step before it must be accepted."""
    state = played(steps[:-1], options)
    outcome = pushing_step(state, steps[-1], options)
    if outcome.refusal is not None:
        assert outcome.state == state
    return outcome.refusal


def test_a_push_moves_the_turn_on_and_leaves_hands_and_skat() -> None:
    state = played((Push(FOREHAND),))
    assert (state.turn, state.deal, state.pushes, state.result) == (MIDDLEHAND, DEAL, 1, None)


@pytest.mark.parametrize(
    ("rule", "factor"),
    [
        pytest.param(STAY, 8, id="2-jacks-stay"),
        pytest.param(JACKS_MAY_GO, 8, id="3-jacks-may-go"),
        pytest.param(NO_DOUBLING, 1, id="4-no-doubling"),
    ],
)
def test_three_pushes_leave_a_ramsch_on_the_dealt_cards_with_the_rules_factor(rule: PushingRule, factor: int) -> None:
    state = played(PUSH_ALL, options_of(rule))
    assert (state.deal, state.result) == (DEAL, RamschOn())
    assert push_factor(state.pushes, rule) == factor


def test_a_take_and_two_cards_put_back_leave_ten_and_the_two_as_skat() -> None:
    state = played((Take(FOREHAND), Put(FOREHAND, FOREHAND_PLAIN)))
    assert state.turn is MIDDLEHAND
    assert state.deal.skat == FOREHAND_PLAIN
    assert state.deal.forehand == (*DEAL.forehand[2:], *SKAT_CARDS)
    assert push_factor(state.pushes, STAY) == 1


def test_rearhands_cards_put_back_are_the_skat_left_after_a_push_before() -> None:
    state = played(
        (Take(FOREHAND), Put(FOREHAND, FOREHAND_PLAIN), Push(MIDDLEHAND), Take(REARHAND), Put(REARHAND, REARHAND_PLAIN))
    )
    assert state.result == RamschOn()
    assert state.deal.skat == REARHAND_PLAIN
    assert push_factor(state.pushes, STAY) == 2


def test_two_pushes_then_rearhand_takes_and_puts_back_doubles_twice() -> None:
    state = played((Push(FOREHAND), Push(MIDDLEHAND), Take(REARHAND), Put(REARHAND, REARHAND_PLAIN)))
    assert state.result == RamschOn()
    assert state.deal.skat == REARHAND_PLAIN
    assert push_factor(state.pushes, STAY) == 4


@pytest.mark.parametrize("rule", [STAY, NO_DOUBLING])
def test_a_jack_among_the_cards_put_back_is_refused_unless_jacks_may_go(rule: PushingRule) -> None:
    steps = (Take(FOREHAND), Put(FOREHAND, (CLUBS_JACK, FOREHAND_PLAIN[0])))
    assert refused_by(steps, options_of(rule)) is JACK_PUT_BACK


def test_a_jack_may_be_put_back_where_jacks_may_go() -> None:
    state = played((Take(FOREHAND), Put(FOREHAND, (CLUBS_JACK, FOREHAND_PLAIN[0]))), options_of(JACKS_MAY_GO))
    assert CLUBS_JACK in state.deal.skat


@pytest.mark.parametrize(
    ("steps", "refusal"),
    [
        pytest.param((Push(MIDDLEHAND),), NOT_YOUR_TURN, id="10-push"),
        pytest.param((Take(REARHAND),), NOT_YOUR_TURN, id="10-take"),
        pytest.param((DeclareGrandHand(MIDDLEHAND),), NOT_YOUR_TURN, id="10-grand-hand"),
        pytest.param((Take(FOREHAND), Put(MIDDLEHAND, FOREHAND_PLAIN)), NOT_YOUR_TURN, id="10-put"),
        pytest.param((Take(FOREHAND), Push(FOREHAND)), OUT_OF_ORDER, id="11-push-holding-twelve"),
        pytest.param((Put(FOREHAND, FOREHAND_PLAIN),), OUT_OF_ORDER, id="11-put-without-a-take"),
        pytest.param((Take(FOREHAND), Take(FOREHAND)), OUT_OF_ORDER, id="21-second-take"),
        pytest.param((Take(FOREHAND), Put(FOREHAND, FOREHAND_PLAIN[:1])), NOT_TWO, id="12-one-card"),
        pytest.param((Take(FOREHAND), Put(FOREHAND, (FOREHAND_PLAIN[0],) * 2)), NOT_TWO, id="12-the-same-card-twice"),
        pytest.param((Take(FOREHAND), Put(FOREHAND, MIDDLEHAND_PLAIN)), NOT_TWO, id="12-a-card-not-held"),
        pytest.param((Take(FOREHAND), DeclareGrandHand(FOREHAND)), OUT_OF_ORDER, id="17-he-has-looked"),
        pytest.param((*PUSH_ALL, Push(FOREHAND)), OVER, id="13-after-the-ramsch-is-set"),
        pytest.param((DeclareGrandHand(FOREHAND), Push(MIDDLEHAND)), OVER, id="13-after-a-grand-hand"),
    ],
)
def test_a_step_that_does_not_fit_is_refused_and_changes_nothing(
    steps: tuple[PushStep, ...], refusal: PushRefusal
) -> None:
    assert refused_by(steps) is refusal


def test_any_player_declaring_grand_hand_is_refused_where_it_is_off() -> None:
    assert refused_by((DeclareGrandHand(FOREHAND),), options_of(grand_hand=OFF)) is GRAND_HAND_OFF


@pytest.mark.parametrize(
    ("steps", "declarer"),
    [
        pytest.param((DeclareGrandHand(FOREHAND),), FOREHAND, id="14-forehand"),
        pytest.param((Push(FOREHAND), DeclareGrandHand(MIDDLEHAND)), MIDDLEHAND, id="15-middlehand-after-a-push"),
        pytest.param((Push(FOREHAND), Push(MIDDLEHAND), DeclareGrandHand(REARHAND)), REARHAND, id="15-rearhand"),
    ],
)
def test_a_grand_hand_ends_the_stage_at_the_lowest_bid_on_the_cards_as_they_lie(
    steps: tuple[PushStep, ...], declarer: Position
) -> None:
    state = played(steps)
    assert (state.result, state.deal, state.pushes) == (Declared(declarer, LOWEST_BID), DEAL, 0)


def test_a_grand_hand_after_a_put_back_leaves_that_skat_and_the_ten_kept() -> None:
    state = played((Take(FOREHAND), Put(FOREHAND, FOREHAND_PLAIN), DeclareGrandHand(MIDDLEHAND)))
    assert state.result == Declared(MIDDLEHAND, LOWEST_BID)
    assert state.deal.skat == FOREHAND_PLAIN
    assert state.deal.forehand == (*DEAL.forehand[2:], *SKAT_CARDS)


def test_a_grand_hand_instead_is_scored_as_any_grand_hand_at_the_lowest_bid() -> None:
    state = played((DeclareGrandHand(FOREHAND),))
    assert isinstance(state.result, Declared)
    declaring = Declaring.start(state.result, state.deal)
    declaration = declare(declaring, GameKind.GRAND, hand=True, ouvert=False, announcement=Announcement.NONE)
    assert declaration.refusal is None
    playing = start_play(declaration.state, state.deal)
    won_trick = CompletedTrick(
        FOREHAND, (Card(Suit.KARO, Rank.ACE), Card(Suit.HERZ, Rank.TEN), Card(Suit.PIK, Rank.SEVEN)), FOREHAND
    )
    seven = Card(Suit.KARO, Rank.SEVEN)
    lost_trick = CompletedTrick(FOREHAND, (seven, seven, seven), MIDDLEHAND)
    result = PlayedOut(playing.declared, (won_trick,) * 3 + (lost_trick,) * 7)
    settlement = settle(result, LOWEST_BID)
    assert settlement == Settlement(won=True, value=72, score=72)
    assert reckon(settlement) == Reckoning(declarer=122, each_opponent=0)


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param(
            (Take(FOREHAND), Put(FOREHAND, FOREHAND_PLAIN), Push(MIDDLEHAND), Push(REARHAND)), id="stored-log"
        ),
    ],
)
def test_a_stored_log_leads_to_the_state_step_by_step_play_leads_to(steps: tuple[PushStep, ...]) -> None:
    state = Pushing.start(DEAL)
    for step in steps:
        state = pushing_step(state, step, OPTIONS).state
    assert pushing_after(Pushing.start(DEAL), steps, OPTIONS) == state


def test_a_log_with_a_refused_step_raises_naming_the_step_and_the_refusal() -> None:
    with pytest.raises(ValueError, match=r"step 2 refused: not-your-turn"):
        played((Push(FOREHAND), Push(FOREHAND)))
