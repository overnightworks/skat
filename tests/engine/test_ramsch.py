import random
from itertools import pairwise, permutations

import pytest

from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position, deal
from skat.engine.ramsch import (
    RamschPlaying,
    play_ramsch_card,
    ramsch_after,
    start_ramsch,
)
from skat.engine.tricks import CardPlayed, PlayRefusal

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
POSITIONS = (FOREHAND, MIDDLEHAND, REARHAND)
JACKS_BY_STRENGTH = tuple(Card(suit, Rank.JACK) for suit in (Suit.KREUZ, Suit.PIK, Suit.HERZ, Suit.KARO))
SUIT_ORDER = (Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN)
HERZ_KING, PIK_SEVEN = Card(Suit.HERZ, Rank.KING), Card(Suit.PIK, Rank.SEVEN)
HERZ_SEVEN, HERZ_JACK = Card(Suit.HERZ, Rank.SEVEN), Card(Suit.HERZ, Rank.JACK)
KARO_JACK, KREUZ_ACE = Card(Suit.KARO, Rank.JACK), Card(Suit.KREUZ, Rank.ACE)
KARO_ACE, KARO_TEN = Card(Suit.KARO, Rank.ACE), Card(Suit.KARO, Rank.TEN)


def cards_of(suit: Suit, *ranks: Rank) -> tuple[Card, ...]:
    return tuple(Card(suit, rank) for rank in ranks)


def lying_deal() -> Deal:
    """Forehand holds the four jacks and the Kreuz suit from the Ace to the Eight; the skat is Karo Ace and Ten."""
    forehand = (
        *JACKS_BY_STRENGTH,
        *cards_of(Suit.KREUZ, Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT),
    )
    skat = (KARO_ACE, KARO_TEN)
    rest = [card for card in DECK if card not in {*forehand, *skat}]
    return Deal(forehand=forehand, middlehand=tuple(rest[:10]), rearhand=tuple(rest[10:]), skat=skat)


def holding(forehand: tuple[Card, ...], middlehand: tuple[Card, ...], rearhand: tuple[Card, ...]) -> RamschPlaying:
    """A Ramsch in which each player holds only the given cards, forehand to lead."""
    return RamschPlaying(
        hands={FOREHAND: forehand, MIDDLEHAND: middlehand, REARHAND: rearhand},
        leader=FOREHAND,
        current=(),
        tricks=(),
        result=None,
        skat=(),
    )


def play_all(state: RamschPlaying, plays: tuple[Card, ...]) -> RamschPlaying:
    for card in plays:
        outcome = play_ramsch_card(state, state.turn, card)
        assert outcome.refusal is None
        state = outcome.state
    return state


def play_out(state: RamschPlaying) -> tuple[RamschPlaying, tuple[CardPlayed, ...]]:
    """Play every turn the first card of the hand that the rules accept."""
    steps: list[CardPlayed] = []
    while state.result is None:
        for card in state.hands[state.turn]:
            outcome = play_ramsch_card(state, state.turn, card)
            if outcome.refusal is None:
                steps.append(CardPlayed(state.turn, card))
                state = outcome.state
                break
    return state, tuple(steps)


def test_a_ramsch_starts_with_forehand_to_lead_and_the_skat_in_no_hand() -> None:
    cards = lying_deal()

    state = start_ramsch(cards)

    assert state.turn is FOREHAND
    assert dict(state.hands) == dict(cards.hands)
    assert state.skat == cards.skat
    assert all(len(hand) == 10 for hand in state.hands.values())
    assert not any(card in hand for hand in state.hands.values() for card in cards.skat)


def test_the_karo_jack_takes_a_trick_against_the_ace_of_the_suit_led() -> None:
    state = holding((KARO_ACE,), (KARO_JACK,), (PIK_SEVEN,))

    state = play_all(state, (KARO_ACE, KARO_JACK, PIK_SEVEN))

    assert state.tricks[0].taker is MIDDLEHAND


@pytest.mark.parametrize(
    "trick",
    [pytest.param(trick, id=" ".join(f"{c.suit.name}" for c in trick)) for trick in permutations(JACKS_BY_STRENGTH, 3)],
)
def test_the_jacks_rank_kreuz_pik_herz_karo(trick: tuple[Card, Card, Card]) -> None:
    state = holding((trick[0],), (trick[1],), (trick[2],))
    strongest = min(trick, key=JACKS_BY_STRENGTH.index)

    state = play_all(state, trick)

    assert state.tricks[0].taker is POSITIONS[trick.index(strongest)]


@pytest.mark.parametrize(("higher", "lower"), list(pairwise(SUIT_ORDER)))
def test_a_card_higher_in_the_suit_order_takes_the_trick_without_trump(higher: Rank, lower: Rank) -> None:
    state = holding((Card(Suit.HERZ, lower),), (Card(Suit.HERZ, higher),), (PIK_SEVEN,))

    state = play_all(state, (Card(Suit.HERZ, lower), Card(Suit.HERZ, higher), PIK_SEVEN))

    assert state.tricks[0].taker is MIDDLEHAND


def test_a_player_holding_the_suit_led_must_follow_it() -> None:
    state = play_all(holding((HERZ_KING,), (HERZ_SEVEN, PIK_SEVEN), (KARO_ACE,)), (HERZ_KING,))

    outcome = play_ramsch_card(state, MIDDLEHAND, PIK_SEVEN)

    assert outcome.refusal is PlayRefusal.MUST_FOLLOW
    assert outcome.state == state


@pytest.mark.parametrize("card", [HERZ_JACK, PIK_SEVEN])
def test_the_herz_jack_is_trump_so_a_player_holding_no_other_herz_may_play_any_card(card: Card) -> None:
    state = play_all(holding((HERZ_KING,), (HERZ_JACK, PIK_SEVEN), (KARO_ACE,)), (HERZ_KING,))

    outcome = play_ramsch_card(state, MIDDLEHAND, card)

    assert outcome.refusal is None


@pytest.mark.parametrize(
    ("position", "card", "refusal"),
    [
        (MIDDLEHAND, PIK_SEVEN, PlayRefusal.NOT_YOUR_TURN),
        (FOREHAND, HERZ_JACK, PlayRefusal.NOT_IN_HAND),
    ],
)
def test_a_card_out_of_turn_or_out_of_hand_changes_nothing(
    position: Position, card: Card, refusal: PlayRefusal
) -> None:
    state = holding((HERZ_KING,), (PIK_SEVEN,), (KARO_ACE,))

    outcome = play_ramsch_card(state, position, card)

    assert (outcome.refusal, outcome.state) == (refusal, state)


def test_each_trick_counts_for_its_own_taker_and_the_taker_leads_next() -> None:
    karo, herz, pik = (
        Card(suit, rank) for suit, rank in ((Suit.KARO, Rank.SEVEN), (Suit.HERZ, Rank.SEVEN), (Suit.PIK, Rank.SEVEN))
    )
    state = holding(
        (karo, Card(Suit.HERZ, Rank.EIGHT), Card(Suit.PIK, Rank.NINE)),
        (Card(Suit.KARO, Rank.NINE), herz, Card(Suit.PIK, Rank.EIGHT)),
        (Card(Suit.KARO, Rank.EIGHT), Card(Suit.HERZ, Rank.NINE), pik),
    )
    leaders = []

    for plays in (
        (karo, Card(Suit.KARO, Rank.NINE), Card(Suit.KARO, Rank.EIGHT)),
        (herz, Card(Suit.HERZ, Rank.NINE), Card(Suit.HERZ, Rank.EIGHT)),
        (pik, Card(Suit.PIK, Rank.NINE), Card(Suit.PIK, Rank.EIGHT)),
    ):
        state = play_all(state, plays)
        leaders.append(state.leader)

    assert [trick.taker for trick in state.tricks] == [MIDDLEHAND, REARHAND, FOREHAND]
    assert leaders == [MIDDLEHAND, REARHAND, FOREHAND]


def test_the_tenth_trick_ends_the_ramsch_with_every_count() -> None:
    cards = lying_deal()

    state, _ = play_out(start_ramsch(cards))

    result = state.result
    assert result is not None
    assert [result.tricks_of(position) for position in POSITIONS] == [10, 0, 0]
    assert [result.points_of(position) for position in POSITIONS] == [99, 0, 0]
    assert result.last_trick_taker is FOREHAND
    assert result.skat == cards.skat


@pytest.mark.parametrize("seed", range(5))
def test_all_card_points_are_the_players_or_the_skats(seed: int) -> None:
    cards = deal(random.Random(seed))  # noqa: S311 - seeded shuffle keeps the deal reproducible

    state, _ = play_out(start_ramsch(cards))

    result = state.result
    assert result is not None
    assert sum(result.tricks_of(position) for position in POSITIONS) == 10
    skat_points = sum(card.points for card in cards.skat)
    assert sum(result.points_of(position) for position in POSITIONS) == 120 - skat_points


def test_a_card_after_the_tenth_trick_is_refused_as_over() -> None:
    state, _ = play_out(start_ramsch(lying_deal()))

    outcome = play_ramsch_card(state, FOREHAND, KREUZ_ACE)

    assert outcome.refusal is PlayRefusal.OVER


@pytest.mark.parametrize("seed", range(3))
def test_a_stored_log_of_thirty_cards_replays_to_the_same_state(seed: int) -> None:
    start = start_ramsch(deal(random.Random(seed)))  # noqa: S311 - seeded shuffle keeps the deal reproducible
    played, steps = play_out(start)

    assert len(steps) == 30
    assert ramsch_after(start, steps) == played


def test_a_log_the_rules_refuse_raises_naming_the_step_and_the_reason() -> None:
    start = holding((HERZ_KING,), (HERZ_SEVEN, PIK_SEVEN), (KARO_ACE,))
    steps = (CardPlayed(FOREHAND, HERZ_KING), CardPlayed(MIDDLEHAND, PIK_SEVEN))

    with pytest.raises(ValueError, match="step 2 refused: must-follow"):
        ramsch_after(start, steps)
