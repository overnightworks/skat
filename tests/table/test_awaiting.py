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
    GiveUpAsked,
    HandProgress,
    RamschOccasion,
    RamschSetting,
    Series,
    TableId,
    TableOptions,
)
from skat.table.views import view_of
from tests.support.played_game import after_the_first_game, declared_herz_hand, table_in

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


def between_games(*ready_seats, series=None, proposal=None):
    table = after_the_first_game(table_in(HandProgress()), *ready_seats)
    return replace(table, series=series or replace(Series(12, 1), end_proposal=proposal))


def over_series():
    return Series(12, 12)


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
    def asked_by_the_declarer(self, declined_by=None):
        table = table_in(declared_herz_hand())
        asked = GiveUpAsked(Position.MIDDLEHAND, declined_by)
        return replace(table, progress=replace(table.progress, give_up=asked))

    def test_an_opponent_who_has_not_answered_is_awaited_though_it_is_not_on_turn(self):
        assert waiting_for(self.asked_by_the_declarer()) == {FOREHAND, REARHAND}

    def test_the_opponent_who_declined_and_the_asker_are_not_awaited(self):
        table = self.asked_by_the_declarer(declined_by=Position.REARHAND)

        assert REARHAND not in waiting_for(table)
        assert MIDDLEHAND not in waiting_for(table)


class TestAResultAndTheEndOfTheSeries:
    def test_a_result_awaits_every_seat_that_has_not_continued(self):
        assert waiting_for(between_games(SEAT_OF[REARHAND])) == {MIDDLEHAND, FOREHAND}

    def test_a_result_awaits_nobody_once_every_seat_continued(self):
        assert waiting_for(between_games(1, 2, 3)) == set()

    def test_the_end_of_the_series_awaits_every_seat_that_has_not_marked_new_series(self):
        assert waiting_for(between_games(SEAT_OF[MIDDLEHAND], series=over_series())) == {REARHAND, FOREHAND}

    def test_a_series_that_ended_early_awaits_the_unmarked_seats_like_a_series_that_ran_out(self):
        table = between_games(series=Series(12, 1, ended_early=True))

        assert waiting_for(table) == set(EVERYONE)

    def test_a_series_over_awaits_nobody_once_every_seat_marked(self):
        assert waiting_for(between_games(1, 2, 3, series=over_series())) == set()


class TestAnEarlyEndProposal:
    def proposed_by(self, seat, accepter=None):
        return between_games(1, 2, 3, proposal=EndProposal(seat, accepter))

    def test_the_seats_that_have_not_answered_are_awaited(self):
        assert waiting_for(self.proposed_by(1)) == {REARHAND, FOREHAND}

    def test_the_proposer_and_the_accepter_are_not_awaited(self):
        assert waiting_for(self.proposed_by(1, accepter=2)) == {FOREHAND}


class TestNothingIsAwaited:
    def test_a_free_chair_is_not_awaited_and_the_result_awaits_only_the_seated(self):
        table = between_games()
        freed = replace(table, chairs=(Chair(1, None), *table.chairs[1:]))

        assert waiting_for(freed) == {REARHAND, FOREHAND}

    def test_a_passed_in_hand_awaits_nobody_while_it_pauses(self):
        table = replace(table_in(HandProgress(ALL_PASS)), hand=None)

        assert waiting_for(table) == set()

    def test_a_table_with_fewer_than_three_chairs_and_no_result_awaits_nobody(self):
        table = table_in(HandProgress())
        two = replace(table, hand=None, chairs=(table.chairs[0], table.chairs[1], Chair(3, None)))

        assert waiting_for(two) == set()

    def test_an_account_without_a_chair_is_not_awaited(self):
        view = view_of(between_games(), "account-watcher", frozenset({"account-watcher"}))

        assert awaits_you(view) is False

    def test_an_ended_table_awaits_nobody(self):
        ended = EndedTable(TableId("0" * 32), 9, EndReason.EMPTY, 3600)

        assert awaits_you(view_of(ended, MIDDLEHAND, frozenset())) is False
