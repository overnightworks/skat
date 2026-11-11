"""Whether the table waits for a seat is decided from the seat's own view, in seven cases."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.declaration import Announcement, Declare, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.table.awaiting import awaits_you
from skat.table.records import (
    Chair,
    EndedTable,
    EndProposal,
    EndReason,
    HandProgress,
    RamschOccasion,
    RamschSetting,
    Series,
    TableId,
    TableOptions,
)
from skat.table.rules import decide_sit
from skat.table.views import view_of
from tests.support.open_chairs import PHASES, REARHAND_SEAT, newcomer, sent_away
from tests.support.played_game import asked_by_the_declarer, between_games, declared_herz_hand, table_in

MIDDLEHAND, REARHAND, FOREHAND = "account-middlehand", "account-rearhand", "account-forehand"
EVERYONE = (MIDDLEHAND, REARHAND, FOREHAND)
# Seat 2 deals, so the seats 1, 2 and 3 are middlehand, rearhand and forehand.
SEAT_OF = {MIDDLEHAND: 1, REARHAND: 2, FOREHAND: 3}
RAMSCH = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.SKAT_TO_LOSER, JungfrauRule.OFF, DurchmarschRule.WINS_120_FLAT),
    )
)
ALL_PASS = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
HERZ_HAND = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
DECLARER_BID = (Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND))


def waiting_for(table):
    """The accounts of the seated whose own view says the table waits for them."""
    return {account for account in EVERYONE if awaits_you(view_of(table, account, frozenset()))}


class TestTheTurnOfTheHand:
    @pytest.mark.parametrize(
        ("progress", "options", "waiting"),
        [
            pytest.param(HandProgress(), None, {MIDDLEHAND}, id="auction-first-bid"),
            pytest.param(HandProgress((Bid(Position.MIDDLEHAND, 18),)), None, {FOREHAND}, id="auction-answer"),
            pytest.param(HandProgress(DECLARER_BID), None, {MIDDLEHAND}, id="declarer-takes-the-skat"),
            pytest.param(
                HandProgress(DECLARER_BID, declaring=(TakeSkat(),)), None, {MIDDLEHAND}, id="declarer-puts-back"
            ),
            pytest.param(declared_herz_hand(), None, {FOREHAND}, id="play-forehand-leads"),
            pytest.param(HandProgress(ALL_PASS), RAMSCH, {FOREHAND}, id="ramsch-play"),
        ],
    )
    def test_the_seat_on_turn_is_awaited_and_no_other(self, progress, options, waiting):
        table = table_in(progress, options)

        assert waiting_for(table) == waiting

    def test_the_declarer_is_still_awaited_after_the_skat_went_back_until_the_game_is_declared(self):
        table = table_in(HandProgress(DECLARER_BID, declaring=(TakeSkat(), PutBack(DECK[30:32]))))

        assert MIDDLEHAND in waiting_for(table)


class TestAGiveUpQuestion:
    @pytest.mark.parametrize(
        ("declined_by", "waiting"),
        [
            pytest.param(None, {FOREHAND, REARHAND}, id="an-opponent-who-has-not-answered-though-not-on-turn"),
            pytest.param(Position.REARHAND, {FOREHAND}, id="not-the-opponent-who-declined-nor-the-asker"),
        ],
    )
    def test_the_opponents_who_have_not_answered_are_awaited(self, declined_by, waiting):
        assert waiting_for(asked_by_the_declarer(declined_by)) == waiting


class TestAResultAndTheEndOfTheSeries:
    @pytest.mark.parametrize(
        ("table", "waiting"),
        [
            pytest.param(
                between_games(SEAT_OF[REARHAND]), {MIDDLEHAND, FOREHAND}, id="a-result-awaits-who-has-not-continued"
            ),
            pytest.param(between_games(1, 2, 3), set(), id="a-result-awaits-nobody-once-all-continued"),
            pytest.param(
                between_games(SEAT_OF[MIDDLEHAND], series=Series(12, 12)),
                {REARHAND, FOREHAND},
                id="a-series-over-awaits-who-has-not-marked-new-series",
            ),
            pytest.param(
                between_games(series=Series(12, 1, ended_early=True)),
                set(EVERYONE),
                id="a-series-ended-early-awaits-the-unmarked-like-one-that-ran-out",
            ),
            pytest.param(
                between_games(1, 2, 3, series=Series(12, 12)), set(), id="a-series-over-awaits-nobody-once-all-marked"
            ),
        ],
    )
    def test_the_seats_that_have_not_answered_the_result_are_awaited(self, table, waiting):
        assert waiting_for(table) == waiting


class TestAnEarlyEndProposal:
    @pytest.mark.parametrize(
        ("proposal", "waiting"),
        [
            pytest.param(EndProposal(1), {REARHAND, FOREHAND}, id="the-seats-that-have-not-answered"),
            pytest.param(EndProposal(1, accepter=2), {FOREHAND}, id="not-the-proposer-nor-the-accepter"),
        ],
    )
    def test_the_seats_that_have_not_answered_are_awaited(self, proposal, waiting):
        assert waiting_for(between_games(1, 2, 3, proposal=proposal)) == waiting


def with_a_free_first_chair(table):
    return replace(table, chairs=(Chair(1, None), *table.chairs[1:]))


def with_a_free_third_chair(table):
    return replace(table, hand=None, chairs=(table.chairs[0], table.chairs[1], Chair(3, None)))


class TestNothingIsAwaited:
    @pytest.mark.parametrize(
        ("table", "waiting"),
        [
            pytest.param(
                with_a_free_first_chair(between_games()), {REARHAND, FOREHAND}, id="a-free-chair-is-not-awaited"
            ),
            pytest.param(
                replace(table_in(HandProgress(ALL_PASS)), hand=None), set(), id="a-passed-in-hand-while-it-pauses"
            ),
            pytest.param(
                with_a_free_third_chair(table_in(HandProgress())), set(), id="fewer-than-three-chairs-and-no-result"
            ),
        ],
    )
    def test_the_seats_that_nothing_waits_for_are_not_awaited(self, table, waiting):
        assert waiting_for(table) == waiting

    def test_an_account_without_a_chair_is_not_awaited(self):
        view = view_of(between_games(), "account-watcher", frozenset({"account-watcher"}))

        assert awaits_you(view) is False

    def test_an_ended_table_awaits_nobody(self):
        ended = EndedTable(TableId("0" * 32), 9, EndReason.EMPTY, 3600)

        assert awaits_you(view_of(ended, MIDDLEHAND, frozenset())) is False


class TestAnOpenChair:
    """The hand waits for a sitter, so no seat is awaited and the revision rises when one joins."""

    @pytest.mark.parametrize("phase", PHASES)
    def test_no_seat_is_awaited_while_a_chair_of_the_running_hand_is_open(self, phase):
        running = PHASES[phase]()
        waiting = sent_away(running, REARHAND_SEAT)

        assert waiting_for(running)
        assert waiting_for(waiting) == set()

    def test_no_seat_is_awaited_for_a_give_up_question_either(self):
        asked = asked_by_the_declarer()

        assert waiting_for(sent_away(asked, REARHAND_SEAT)) == set()

    def test_the_seat_on_turn_is_awaited_again_under_a_higher_revision_once_a_sitter_joins(self):
        running = PHASES["auction"]()
        waiting = sent_away(running, SEAT_OF[REARHAND])
        sitter = newcomer()

        taken = decide_sit(waiting, sitter, SEAT_OF[REARHAND], None).table

        assert waiting_for(taken) == waiting_for(running)
        assert taken.version > waiting.version
