from dataclasses import replace

import pytest

from skat.engine.bidding import Pass, PassedIn
from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.deal import Position
from skat.engine.tricks import play_card
from skat.table.auction import AuctionAction, AuctionCommand, decide_step
from skat.table.bock import BockView, bock_after, bock_view_of
from skat.table.hand_state import playing_of
from skat.table.records import Actor, HandProgress, Series, TableOptions
from tests.support.played_game import an_entry, before_the_last_card, table_in

APPEND, MULTIPLY, IGNORE = BockOverlap.APPEND, BockOverlap.MULTIPLY, BockOverlap.IGNORE
PASSED_IN, TOTAL_ENDING_IN_00 = BockTrigger.PASSED_IN, BockTrigger.TOTAL_ENDING_IN_00
SEAT_ACCOUNTS = ("account-middlehand", "account-rearhand", "account-forehand")


def bock_table(triggers=(PASSED_IN,), overlap=APPEND, *, rounds=(), series=None, game_list=(), progress=None):
    options = TableOptions(bock=BockOptions(frozenset(triggers), overlap))
    table = table_in(HandProgress() if progress is None else progress, options)
    return replace(table, bock=BockRounds(rounds), series=series, game_list=game_list)


def entry(seat, *, won, score):
    """An entry of the table's three accounts whose declarer sits in `seat`."""
    return replace(an_entry(SEAT_ACCOUNTS), declarer_seat=seat, won=won, score=score)


def the_game_just_ended():
    """What the last card of a played game leaves: the engine's result for the table's declared game."""
    table, last = before_the_last_card(table_in(HandProgress()))
    state = playing_of(table)
    return play_card(state, last.position, last.card).state.result


class TestTheTotalEndingIn00:
    """Seat 1's total before this game, the entry this game writes, and whether seat 1's total now ends in 00."""

    @pytest.mark.parametrize(
        ("earlier", "this_game", "rounds"),
        [
            pytest.param(entry(1, won=True, score=150), entry(2, won=True, score=36), (), id="stays-at-200"),
            pytest.param(entry(1, won=True, score=140), entry(1, won=True, score=-30), (), id="190-to-210"),
            pytest.param(entry(1, won=True, score=0), entry(1, won=False, score=0), (), id="50-to-0"),
            pytest.param(entry(1, won=True, score=70), entry(1, won=True, score=30), (3,), id="120-to-200"),
        ],
    )
    def test_it_triggers_only_when_this_game_moved_a_total_to_a_non_zero_multiple_of_100(
        self, earlier, this_game, rounds
    ):
        table = bock_table((TOTAL_ENDING_IN_00,), game_list=(earlier,))

        assert bock_after(table, the_game_just_ended(), this_game) == BockRounds(rounds)


class TestThePendingGamesAfterAHand:
    def test_a_passed_in_hand_with_the_trigger_on_makes_three_bock_games(self):
        assert bock_after(bock_table(), PassedIn(), None) == BockRounds((3,))

    def test_a_passed_in_hand_with_the_trigger_off_makes_none(self):
        table = bock_table((BockTrigger.RE,))

        assert bock_after(table, PassedIn(), None) == BockRounds(())

    def test_a_table_without_bock_keeps_no_pending_game(self):
        table = replace(bock_table(), options=TableOptions())

        assert bock_after(table, PassedIn(), None) == BockRounds(())

    @pytest.mark.parametrize(
        ("overlap", "pending"),
        [(APPEND, (2, 3)), (MULTIPLY, (2, 3)), (IGNORE, (2,))],
        ids=["append", "multiply", "ignore"],
    )
    def test_a_trigger_inside_a_round_acts_as_the_overlap_says(self, overlap, pending):
        table = bock_table(overlap=overlap, rounds=(3,))

        assert bock_after(table, PassedIn(), None) == BockRounds(pending)

    def test_the_last_game_of_the_series_lets_every_round_lapse(self):
        table = bock_table(rounds=(3,), series=Series(3, 3))

        assert bock_after(table, PassedIn(), None) == BockRounds(())

    def test_a_game_before_the_last_keeps_the_round_it_started(self):
        table = bock_table(series=Series(3, 2))

        assert bock_after(table, PassedIn(), None) == BockRounds((3,))


def one_hand_before_the_third_pass(table):
    steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND))
    return replace(table, progress=HandProgress(auction=steps))


class TestThePassedInHandAsksTheTrigger:
    def test_the_third_pass_stores_the_pending_games_with_the_hand_that_ends(self):
        table = one_hand_before_the_third_pass(bock_table())
        command = AuctionCommand("pass-3", table.id.value, table.version, AuctionAction.PASS, None)

        decision = decide_step(table, Actor("account-forehand", "Forehand"), command)

        assert decision.refusal is None
        assert decision.table.bock == BockRounds((3,))


class TestTheViewOfThePendingGames:
    def test_a_table_without_bock_has_none(self):
        assert bock_view_of(replace(bock_table(), options=TableOptions())) is None

    def test_nothing_pending_is_no_game_left_and_factor_1(self):
        assert bock_view_of(bock_table()) == BockView(games_left=0, factor=1)

    @pytest.mark.parametrize(
        ("overlap", "rounds", "view"),
        [
            pytest.param(APPEND, (3,), BockView(3, 2), id="append-one-round"),
            pytest.param(APPEND, (2, 3), BockView(5, 2), id="append-two-rounds"),
            pytest.param(MULTIPLY, (2, 3), BockView(3, 4), id="multiply-two-rounds"),
            pytest.param(IGNORE, (3,), BockView(3, 2), id="ignore"),
        ],
    )
    def test_the_games_left_and_the_factor_follow_the_overlap(self, overlap, rounds, view):
        assert bock_view_of(bock_table(overlap=overlap, rounds=rounds)) == view

    @pytest.mark.parametrize(
        ("series", "running", "games_left"),
        [
            pytest.param(Series(6, 5), False, 1, id="one-game-to-come-between-hands"),
            pytest.param(Series(6, 5), True, 2, id="the-running-game-counts"),
            pytest.param(Series(6, 6), True, 1, id="the-last-game-running"),
            pytest.param(Series(6, 2), False, 3, id="the-series-reaches-further-than-the-round"),
        ],
    )
    def test_it_never_counts_a_game_the_series_will_not_deal(self, series, running, games_left):
        table = bock_table(rounds=(3,), series=series)
        table = table if running else replace(table, hand=None)

        assert bock_view_of(table).games_left == games_left
