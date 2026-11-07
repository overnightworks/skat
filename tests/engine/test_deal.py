import random
from collections.abc import MutableSequence

import pytest

from skat.engine.cards import DECK
from skat.engine.deal import Position, deal, next_dealer, positions_from


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
    dealt = deal(random.Random(7))
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
    assert deal(random.Random(42)) == deal(random.Random(42))


def test_over_many_seeded_deals_every_card_reaches_every_position_and_the_skat():
    reached: dict[object, set[object]] = {card: set() for card in DECK}
    for seed in range(200):
        dealt = deal(random.Random(seed))
        for position, hand in dealt.hands.items():
            for card in hand:
                reached[card].add(position)
        for card in dealt.skat:
            reached[card].add("skat")
    assert all(len(places) == 4 for places in reached.values())


@pytest.mark.parametrize("dealer", [0, 4])
def test_a_seat_outside_one_to_three_is_refused(dealer):
    with pytest.raises(ValueError):
        positions_from(dealer=dealer)
