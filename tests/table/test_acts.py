from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, Hold, Pass, Play
from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.declaration import Announcement, Declaration, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.engine.kontra import Word, WordSaid
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import DeclareGrandHand, GrandHandRule, Push, PushingRule, Put, Take
from skat.engine.tricks import CardPlayed
from skat.table.acts import ActKind, acts_of, next_seq_of
from skat.table.game_list import GameEnding
from skat.table.records import GiveUpAsked, HandProgress, RamschOccasion, RamschSetting, Series, TableOptions
from tests.support.played_game import (
    HERZ_HAND,
    a_ramsch_entry,
    after_a_game,
    after_the_first_game,
    an_entry,
    declared_herz_hand,
    table_in,
)

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Seat 2 deals in `table_in`: seat 3 is forehand, seat 1 middlehand and seat 2 rearhand.
FOREHAND_SEAT, MIDDLEHAND_SEAT, REARHAND_SEAT, DEALER_SEAT = 3, 1, 2, 2
HAND_SPAN = 1000
A_STAGE_WITH_GRAND_HAND = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120),
        PushingRule.JACKS_STAY,
        GrandHandRule.ALLOWED,
    )
)


def a_hand(progress=None, series=Series(36, 1), options=None):  # noqa: B008 - Series is frozen
    return replace(table_in(progress or HandProgress(), options), series=series)


def kinds(table):
    return [each.kind for each in acts_of(table)]


class TestWhatHappenedInTheRunningHand:
    def test_a_dealt_hand_holds_one_line_the_table_says_with_the_dealers_seat(self):
        (deal,) = acts_of(a_hand())

        assert (deal.kind, deal.seat, deal.detail) == (ActKind.DEAL, None, DEALER_SEAT)

    def test_each_auction_step_is_a_line_of_the_seat_that_took_it_in_the_order_taken(self):
        steps = (Bid(MIDDLEHAND, 18), Hold(FOREHAND), Bid(MIDDLEHAND, 20), Pass(FOREHAND))
        table = a_hand(HandProgress(auction=steps))

        assert [(each.kind, each.seat, each.detail) for each in acts_of(table)[1:]] == [
            (ActKind.BID, MIDDLEHAND_SEAT, 18),
            (ActKind.HOLD, FOREHAND_SEAT, 18),
            (ActKind.BID, MIDDLEHAND_SEAT, 20),
            (ActKind.PASS, FOREHAND_SEAT, None),
        ]

    def test_the_forehand_who_plays_at_the_lowest_bid_bids_it(self):
        steps = (Pass(MIDDLEHAND), Pass(REARHAND), Play(FOREHAND))
        table = a_hand(HandProgress(auction=steps))

        assert [(each.kind, each.detail) for each in acts_of(table)[-1:]] == [(ActKind.BID, 18)]

    def test_the_declarers_steps_follow_the_auction_and_a_put_back_names_no_card(self):
        declared = replace(HERZ_HAND, hand=False)
        table = a_hand(replace(declared_herz_hand(), declaring=(TakeSkat(), PutBack((DECK[30], DECK[31])), declared)))

        declaring = acts_of(table)[4:]
        assert [(each.kind, each.seat) for each in declaring] == [
            (ActKind.TAKE_SKAT, MIDDLEHAND_SEAT),
            (ActKind.PUT_BACK, MIDDLEHAND_SEAT),
            (ActKind.DECLARE, MIDDLEHAND_SEAT),
        ]
        assert declaring[1].detail is None
        assert declaring[2].detail == Declaration(
            GameKind.HERZ, hand=False, ouvert=False, announcement=Announcement.NONE
        )

    def test_the_stage_before_a_ramsch_is_a_line_for_each_step_and_a_grand_hand_is_a_declaration(self):
        steps = (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))
        pushing = (Take(FOREHAND), Put(FOREHAND, (DECK[0], DECK[1])), Push(MIDDLEHAND), DeclareGrandHand(REARHAND))
        table = a_hand(HandProgress(auction=steps, pushing=pushing), options=A_STAGE_WITH_GRAND_HAND)

        stage = acts_of(table)[4:]
        assert [(each.kind, each.seat) for each in stage] == [
            (ActKind.TAKE_SKAT, FOREHAND_SEAT),
            (ActKind.PUT_BACK, FOREHAND_SEAT),
            (ActKind.PUSH, MIDDLEHAND_SEAT),
            (ActKind.DECLARE, REARHAND_SEAT),
        ]

    def test_words_stand_between_the_cards_they_were_said_after_and_before(self):
        first, second, third = (
            CardPlayed(FOREHAND, DECK[0]),
            CardPlayed(MIDDLEHAND, DECK[10]),
            CardPlayed(REARHAND, DECK[20]),
        )
        progress = replace(
            declared_herz_hand(),
            plays=(first, second, third),
            words=(
                WordSaid(REARHAND, Word.KONTRA, 0),
                WordSaid(MIDDLEHAND, Word.RE, 2),
                WordSaid(REARHAND, Word.SUPRA, 3),
            ),
        )

        played = acts_of(a_hand(progress))[5:]
        assert [(each.kind, each.detail) for each in played] == [
            (ActKind.WORD, Word.KONTRA),
            (ActKind.PLAY, first.card),
            (ActKind.PLAY, second.card),
            (ActKind.WORD, Word.RE),
            (ActKind.PLAY, third.card),
            (ActKind.WORD, Word.SUPRA),
        ]

    def test_a_give_up_that_stands_unanswered_is_no_line(self):
        table = a_hand(declared_herz_hand())
        asked = replace(table, progress=replace(table.progress, give_up=GiveUpAsked(MIDDLEHAND, REARHAND)))

        assert acts_of(asked) == acts_of(table)


class TestNumbering:
    def test_the_lines_of_a_hand_are_numbered_from_one_above_the_hand_number_in_order(self):
        table = a_hand(declared_herz_hand(), Series(36, 5))

        assert [each.seq for each in acts_of(table)] == [5 * HAND_SPAN + slot for slot in range(1, 6)]

    @pytest.mark.parametrize(
        ("earlier", "later"),
        [
            pytest.param(Series(36, 4), Series(36, 5), id="the-next-deal"),
            pytest.param(Series(99, 99), Series(99, 1, number=2), id="the-next-series"),
        ],
    )
    def test_a_later_hand_numbers_all_its_lines_above_every_line_of_an_earlier_one(self, earlier, later):
        before = acts_of(a_hand(replace(declared_herz_hand(), plays=(CardPlayed(FOREHAND, DECK[0]),)), earlier))
        after = acts_of(a_hand(HandProgress(), later))

        assert min(each.seq for each in after) > max(each.seq for each in before)

    def test_a_table_that_keeps_no_series_numbers_no_hand_and_holds_no_line(self):
        table = a_hand(series=None)

        assert (acts_of(table), next_seq_of(table)) == ((), 1)

    def test_before_the_first_deal_the_next_line_is_the_first_of_the_first_hand(self):
        table = replace(a_hand(series=Series(36, 0)), hand=None, dealer=None)

        assert (acts_of(table), next_seq_of(table)) == ((), HAND_SPAN + 1)


class TestHandsThatEnd:
    def test_a_result_is_the_last_line_of_its_hand_whatever_the_hand_had_before_it(self):
        running = a_hand(declared_herz_hand(), Series(36, 3))
        ended = replace(after_the_first_game(running), series=Series(36, 3))

        (result,) = acts_of(ended)
        assert (result.kind, result.seat, result.seq) == (ActKind.RESULT, None, 3 * HAND_SPAN + 999)
        assert max(each.seq for each in acts_of(running)) < result.seq

    @pytest.mark.parametrize(
        ("ending", "kind"),
        [
            pytest.param(GameEnding.GIVEN_UP, ActKind.GIVE_UP, id="given-up"),
            pytest.param(GameEnding.THROWN_DOWN, ActKind.THROW_DOWN, id="thrown-down"),
        ],
    )
    def test_a_game_given_up_or_thrown_down_says_who_ended_it_before_its_result(self, ending, kind):
        entry = replace(an_entry(), ending=ending, ended_by_seat=2)
        ended = replace(after_a_game(a_hand(), entry), series=Series(36, 3))

        assert [(each.kind, each.seat) for each in acts_of(ended)] == [(kind, 2), (ActKind.RESULT, None)]

    def test_a_ramsch_result_is_a_line_too(self):
        ended = replace(after_a_game(a_hand(), a_ramsch_entry()), series=Series(36, 3))

        assert kinds(ended) == [ActKind.RESULT]

    def test_a_hand_passed_in_keeps_its_steps_and_ends_in_a_line(self):
        steps = (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))
        passed_in = replace(a_hand(HandProgress(auction=steps)), hand=None)

        assert kinds(passed_in) == [ActKind.DEAL, ActKind.PASS, ActKind.PASS, ActKind.PASS, ActKind.PASSED_IN]
        assert acts_of(passed_in)[-1].seq % HAND_SPAN == 999

    def test_a_table_whose_hand_ended_with_no_result_holds_no_line(self):
        assert acts_of(replace(a_hand(), hand=None)) == ()

    def test_a_hand_aborted_by_a_vote_leaves_one_line(self):
        aborted = replace(a_hand(HandProgress(aborted=True)), hand=None)

        (line,) = acts_of(aborted)
        assert (line.kind, line.seat, line.seq % HAND_SPAN) == (ActKind.ABORTED, None, 999)
