import pytest

from skat.engine.bidding import (
    LOWEST_BID,
    VALID_BIDS,
    Auction,
    BidOutcome,
    BidRefusal,
    Declared,
    PassedIn,
    bid,
    hold,
    pass_,
    play,
)
from skat.engine.deal import Position

FORE, MID, REAR = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


def run(*steps: tuple) -> BidOutcome:
    outcome = BidOutcome(Auction.start())
    for step in steps:
        action, position, *value = step
        outcome = action(outcome.auction, position, *value)
        assert outcome.refusal is None, step
    return outcome


def declared(outcome: BidOutcome, position: Position, value: int) -> None:
    assert outcome.auction.result == Declared(position, value)


def refused(outcome: BidOutcome, reason: BidRefusal, before: Auction) -> None:
    assert outcome.refusal is reason
    assert outcome.auction == before


def test_lowest_bid_is_18_and_highest_is_264() -> None:
    assert VALID_BIDS[0] == LOWEST_BID == 18
    assert VALID_BIDS[-1] == 264


def test_valid_bids_are_the_63_game_values_from_18_to_264() -> None:
    assert len(VALID_BIDS) == 63
    assert tuple(sorted(set(VALID_BIDS))) == VALID_BIDS
    assert VALID_BIDS[-3:] == (216, 240, 264)
    assert {23, 24} <= set(VALID_BIDS)
    assert not {19, 21, 25, 26} & set(VALID_BIDS)


def test_forehand_invites_middlehand_who_bids_and_forehand_holds_or_passes() -> None:
    outcome = run((bid, MID, 18), (hold, FORE), (bid, MID, 20), (pass_, FORE), (pass_, REAR))
    declared(outcome, MID, 20)


def test_a_bidder_may_skip_values() -> None:
    run((bid, MID, 22))
    run((bid, MID, 18), (hold, FORE), (bid, MID, 24))


@pytest.mark.parametrize("value", [17, 19, 265])
def test_a_bid_that_is_no_game_value_is_refused(value: int) -> None:
    start = Auction.start()
    refused(bid(start, MID, value), BidRefusal.INVALID_VALUE, start)


def test_rearhand_continues_against_middlehands_bid_after_forehand_passes() -> None:
    outcome = run((bid, MID, 20), (pass_, FORE), (bid, REAR, 22), (pass_, MID))
    declared(outcome, REAR, 22)


def test_rearhand_must_bid_above_middlehands_bid() -> None:
    before = run((bid, MID, 20), (pass_, FORE)).auction
    refused(bid(before, REAR, 20), BidRefusal.NOT_ABOVE_STANDING, before)
    assert bid(before, REAR, 22).refusal is None


def test_rearhand_bids_against_forehand_when_middlehand_passes_at_once() -> None:
    outcome = run((pass_, MID), (bid, REAR, 18), (hold, FORE), (bid, REAR, 20), (pass_, FORE))
    declared(outcome, REAR, 20)


def test_rearhand_must_bid_above_the_bid_forehand_held() -> None:
    before = run((bid, MID, 20), (hold, FORE), (pass_, MID)).auction
    refused(bid(before, REAR, 20), BidRefusal.NOT_ABOVE_STANDING, before)
    assert bid(before, REAR, 22).refusal is None


def test_forehand_who_held_is_declarer_when_rearhand_passes_against_him() -> None:
    declared(run((pass_, MID), (bid, REAR, 18), (hold, FORE), (pass_, REAR)), FORE, 18)


def test_middlehand_who_held_is_declarer_when_rearhand_passes() -> None:
    outcome = run((bid, MID, 20), (pass_, FORE), (bid, REAR, 22), (hold, MID), (pass_, REAR))
    declared(outcome, MID, 22)


def test_forehand_holding_middlehands_highest_bid_is_declarer_when_rearhand_passes() -> None:
    declared(run((bid, MID, 20), (hold, FORE), (pass_, MID), (pass_, REAR)), FORE, 20)


ACTIONS = [
    lambda auction, position: pass_(auction, position),
    lambda auction, position: hold(auction, position),
    lambda auction, position: bid(auction, position, 264),
    lambda auction, position: play(auction, position),
]


@pytest.mark.parametrize("act", ACTIONS)
def test_a_position_that_passed_cannot_act_again(act) -> None:
    before = run((bid, MID, 20), (pass_, FORE)).auction
    refused(act(before, FORE), BidRefusal.ALREADY_PASSED, before)


@pytest.mark.parametrize("act", ACTIONS)
def test_nothing_is_taken_back_after_the_auction_is_over(act) -> None:
    before = run((pass_, MID), (pass_, REAR), (pass_, FORE)).auction
    refused(act(before, MID), BidRefusal.OVER, before)
    over_with_declarer = run((bid, MID, 20), (pass_, FORE), (pass_, REAR)).auction
    refused(act(over_with_declarer, MID), BidRefusal.OVER, over_with_declarer)


def test_a_bid_cannot_be_taken_back_by_bidding_lower() -> None:
    before = run((bid, MID, 22), (hold, FORE)).auction
    refused(bid(before, MID, 20), BidRefusal.NOT_ABOVE_STANDING, before)


def test_a_hold_with_no_bid_standing_is_the_wrong_action() -> None:
    start = Auction.start()
    refused(hold(start, MID), BidRefusal.WRONG_ACTION, start)


def test_a_second_hold_in_a_row_is_the_wrong_action() -> None:
    before = run((bid, MID, 18), (hold, FORE)).auction
    refused(hold(before, MID), BidRefusal.WRONG_ACTION, before)


def test_a_play_while_a_bid_stands_is_the_wrong_action() -> None:
    before = run((bid, MID, 18)).auction
    refused(play(before, FORE), BidRefusal.WRONG_ACTION, before)


def test_forehand_plays_at_18_when_middlehand_and_rearhand_bid_nothing() -> None:
    declared(run((pass_, MID), (pass_, REAR), (play, FORE)), FORE, LOWEST_BID)


@pytest.mark.parametrize("act", [pass_, play])
def test_forehand_cannot_act_before_middlehand_has(act) -> None:
    start = Auction.start()
    refused(act(start, FORE), BidRefusal.NOT_YOUR_TURN, start)


@pytest.mark.parametrize("act", [pass_, play])
def test_forehand_cannot_act_before_rearhand_when_middlehand_passed_at_once(act) -> None:
    before = run((pass_, MID)).auction
    refused(act(before, FORE), BidRefusal.NOT_YOUR_TURN, before)


def test_the_hand_is_passed_in_when_all_three_pass() -> None:
    outcome = run((pass_, MID), (pass_, REAR), (pass_, FORE))
    assert outcome.auction.result == PassedIn()


@pytest.mark.parametrize("act", [lambda a, p: bid(a, p, 18), pass_])
def test_rearhand_cannot_act_while_middlehand_and_forehand_are_bidding(act) -> None:
    start = Auction.start()
    refused(act(start, REAR), BidRefusal.NOT_YOUR_TURN, start)
    held = run((bid, MID, 18)).auction
    refused(act(held, REAR), BidRefusal.NOT_YOUR_TURN, held)


def test_refusals_are_checked_in_order() -> None:
    over = run((pass_, MID), (pass_, REAR), (pass_, FORE)).auction
    assert bid(over, FORE, 19).refusal is BidRefusal.OVER
    passed_first = run((bid, MID, 20), (pass_, FORE)).auction
    assert bid(passed_first, FORE, 19).refusal is BidRefusal.ALREADY_PASSED
    assert hold(Auction.start(), FORE).refusal is BidRefusal.NOT_YOUR_TURN
    bid_standing = run((bid, MID, 20)).auction
    assert bid(bid_standing, FORE, 19).refusal is BidRefusal.WRONG_ACTION
    held = run((bid, MID, 20), (hold, FORE)).auction
    assert bid(held, MID, 19).refusal is BidRefusal.INVALID_VALUE
