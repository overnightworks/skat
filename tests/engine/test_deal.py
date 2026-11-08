import random
from typing import TYPE_CHECKING

import pytest

from skat.engine.cards import DECK
from skat.engine.deal import SEATS, Position, deal, draw_dealer, next_dealer, positions_from

if TYPE_CHECKING:
    from collections.abc import MutableSequence


def seeded(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - a seeded source makes the deal reproducible in tests


class KeepsOrder(random.Random):
    def shuffle(self, x: MutableSequence[object]) -> None:
        return None


def test_forehand_is_left_of_the_dealer_and_the_dealer_is_rearhand():
    assert positions_from(dealer=3) == {
        1: Position.FOREHAND,
        2: Position.MIDDLEHAND,
        3: Position.REARHAND,
    }
    assert positions_from(dealer=1) == {
        2: Position.FOREHAND,
        3: Position.MIDDLEHAND,
        1: Position.REARHAND,
    }


def test_next_deal_goes_to_the_next_seat_and_rotates_through_every_seat():
    assert next_dealer(3) == 1
    dealers = [1]
    for _ in range(2):
        dealers.append(next_dealer(dealers[-1]))
    assert sorted(dealers) == [1, 2, 3]


def test_deal_gives_each_player_ten_cards_and_the_skat_two_without_overlap():
    dealt = deal(seeded(7))
    everything = [card for hand in dealt.hands.values() for card in hand] + list(dealt.skat)
    assert [len(hand) for hand in dealt.hands.values()] == [10, 10, 10]
    assert len(dealt.skat) == 2
    assert sorted(everything, key=DECK.index) == list(DECK)


def test_deal_hands_out_three_then_skat_two_then_four_then_three():
    deck = list(DECK)
    dealt = deal(KeepsOrder())
    assert dealt.hands[Position.FOREHAND] == tuple(deck[0:3] + deck[11:15] + deck[23:26])
    assert dealt.hands[Position.MIDDLEHAND] == tuple(deck[3:6] + deck[15:19] + deck[26:29])
    assert dealt.hands[Position.REARHAND] == tuple(deck[6:9] + deck[19:23] + deck[29:32])
    assert dealt.skat == tuple(deck[9:11])


def test_the_same_seeded_source_deals_the_same_hand_twice():
    first = deal(seeded(42))
    second = deal(seeded(42))
    assert first == second


def test_over_many_seeded_deals_every_card_reaches_every_position_and_the_skat():
    reached: dict[object, set[object]] = {card: set() for card in DECK}
    for seed in range(200):
        dealt = deal(seeded(seed))
        for position, hand in dealt.hands.items():
            for card in hand:
                reached[card].add(position)
        for card in dealt.skat:
            reached[card].add("skat")
    assert all(len(places) == 4 for places in reached.values())


@pytest.mark.parametrize("dealer", [0, 4])
def test_a_seat_outside_one_to_three_is_refused(dealer):
    with pytest.raises(ValueError, match="not one of"):
        positions_from(dealer=dealer)


def test_a_dealt_hand_can_be_neither_replaced_nor_removed_and_the_deal_stays_hashable():
    dealt = deal(seeded(1))
    with pytest.raises(TypeError):
        dealt.hands[Position.FOREHAND] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        del dealt.hands[Position.FOREHAND]  # type: ignore[attr-defined]
    assert len(dealt.hands) == 3
    assert hash(dealt) == hash(deal(seeded(1)))
    assert dealt == deal(seeded(1))


def test_the_dealer_is_drawn_from_the_seats_and_the_same_seed_draws_the_same_one():
    first, second = draw_dealer(seeded(5)), draw_dealer(seeded(5))
    assert first in SEATS
    assert first == second


def test_over_many_seeded_draws_every_seat_is_dealer_at_least_once():
    assert {draw_dealer(seeded(seed)) for seed in range(100)} == set(SEATS)


def test_the_dealer_is_drawn_first_so_the_deal_after_it_differs_from_a_deal_on_a_fresh_source():
    source = seeded(11)
    draw_dealer(source)

    assert deal(source) != deal(seeded(11))
