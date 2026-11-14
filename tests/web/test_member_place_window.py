"""The window of a table tells each act as a line of its own sort, in the words of the table's view."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, Hold, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.declaration import PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.engine.kontra import Word, WordSaid
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import GrandHandRule, Push, PushingRule, Put, Take
from skat.engine.tricks import CardPlayed
from skat.table.game_list import GameEnding
from skat.table.member_view import member_acts_of
from skat.table.records import HandProgress, RamschOccasion, RamschSetting, Series, TableOptions
from skat.web.member_place import window_of
from tests.support.played_game import (
    HERZ_HAND,
    a_ramsch_entry,
    after_a_game,
    an_entry,
    declared_herz_hand,
    table_in,
)

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Seat 2 deals in `table_in`: seat 3 is forehand, seat 1 middlehand and seat 2 rearhand.
MIDDLEHAND_ACCOUNT = "account-middlehand"
FIRST_HAND_OF_ITS_SERIES = Series(36, 1)
A_RAMSCH_WITH_PUSHING = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120),
        PushingRule.JACKS_STAY,
        GrandHandRule.OFF,
    )
)


def window_of_table(table, account=MIDDLEHAND_ACCOUNT):
    table = replace(table, series=FIRST_HAND_OF_ITS_SERIES)
    return window_of(member_acts_of(table, account), table.id.value)


def told(window):
    return [(line.name, line.kind, line.text, line.own) for line in window.entries]


def ended(entry):
    return after_a_game(table_in(HandProgress()), entry)


class TestEachActIsALineOfItsKind:
    def test_a_hand_in_play_is_told_act_by_act_with_the_seat_that_took_it(self):
        progress = replace(
            declared_herz_hand(),
            auction=(Bid(MIDDLEHAND, 18), Hold(FOREHAND), Bid(MIDDLEHAND, 20), Pass(FOREHAND), Pass(REARHAND)),
            declaring=(TakeSkat(), PutBack((DECK[30], DECK[31])), replace(HERZ_HAND, hand=False)),
            plays=(CardPlayed(FOREHAND, DECK[0]),),
            words=(WordSaid(REARHAND, Word.KONTRA, 1),),
        )

        window = window_of_table(table_in(progress))

        assert told(window) == [
            ("Table", "deal", "deals a new hand, seat 2 is the dealer", False),
            ("Seat 1", "bid", "bids 18", True),
            ("Seat 3", "hold", "holds 18", False),
            ("Seat 1", "bid", "bids 20", True),
            ("Seat 3", "pass", "passes", False),
            ("Seat 2", "pass", "passes", False),
            ("Seat 1", "take-skat", "takes the skat", True),
            ("Seat 1", "put-back", "puts two cards back", True),
            ("Seat 1", "declare", "declares herz", True),
            ("Seat 3", "play", "plays kreuz seven", False),
            ("Seat 2", "word", "says kontra", False),
        ]
        assert all(line.act and not line.spoken for line in window.entries)

    def test_an_announced_ouvert_game_is_declared_with_its_level(self):
        grand = replace(HERZ_HAND, kind=GameKind.GRAND, ouvert=True)
        progress = replace(declared_herz_hand(), declaring=(grand,))

        assert told(window_of_table(table_in(progress)))[-1][2] == "declares grand hand ouvert schwarz"

    def test_the_stage_before_a_ramsch_tells_a_take_a_put_back_and_a_push(self):
        steps = (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))
        progress = HandProgress(
            auction=steps, pushing=(Take(FOREHAND), Put(FOREHAND, (DECK[0], DECK[1])), Push(MIDDLEHAND))
        )

        window = window_of_table(table_in(progress, A_RAMSCH_WITH_PUSHING))

        assert [line.text for line in window.entries[-3:]] == [
            "takes the skat",
            "puts two cards back",
            "pushes the skat on unseen",
        ]


class TestTheEndOfAHand:
    def test_a_game_played_out_ends_in_a_line_with_the_declarer_the_game_and_the_score(self):
        window = window_of_table(ended(an_entry()))

        assert told(window) == [("Table", "result", "ends the game: seat 1 won kreuz for 36", False)]

    @pytest.mark.parametrize(
        ("ending", "kind", "text"),
        [
            pytest.param(GameEnding.GIVEN_UP, "give-up", "gives up the game", id="given-up"),
            pytest.param(GameEnding.THROWN_DOWN, "throw-down", "throws the cards down", id="thrown-down"),
        ],
    )
    def test_a_game_given_up_or_thrown_down_tells_who_ended_it_before_its_result(self, ending, kind, text):
        window = window_of_table(ended(replace(an_entry(), ending=ending, ended_by_seat=1)))

        assert [(line.name, line.kind, line.text, line.own) for line in window.entries[:1]] == [
            ("Seat 1", kind, text, True)
        ]
        assert window.entries[-1].kind == "result"

    def test_a_lost_game_is_told_as_lost(self):
        window = window_of_table(ended(replace(an_entry(), won=False, score=-72)))

        assert window.entries[-1].text == "ends the game: seat 1 lost kreuz for -72"

    def test_a_ramsch_ends_in_a_line_with_the_score_of_each_seat(self):
        window = window_of_table(ended(a_ramsch_entry()))

        assert told(window) == [
            ("Table", "result", "ends the Ramsch, the scores are seat 1 -47, seat 2 +0, seat 3 +0", False)
        ]

    def test_a_hand_passed_in_ends_in_a_line(self):
        steps = (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))
        passed_in = replace(table_in(HandProgress(auction=steps)), hand=None)

        assert told(window_of_table(passed_in))[-1] == ("Table", "passed-in", "ends the hand: all passed", False)

    def test_a_hand_aborted_by_a_vote_ends_in_a_line(self):
        aborted = replace(table_in(HandProgress(aborted=True)), hand=None)

        assert told(window_of_table(aborted)) == [
            ("Table", "aborted", "ends the hand: the seats voted to abort it", False)
        ]
