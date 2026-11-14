from dataclasses import replace

import pytest

from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschPlayedOut, RamschScoring
from skat.engine.tricks import play_card
from skat.table.bock import BockView, bock_after, bock_view_of
from skat.table.hand_state import playing_of
from skat.table.records import HandProgress, RamschOccasion, RamschSetting, Series, TableOptions
from tests.support.played_game import a_ramsch_entry, an_entry, before_the_last_card, table_in

PASSED_IN, TOTAL_ENDING_IN_00 = BockTrigger.PASSED_IN, BockTrigger.TOTAL_ENDING_IN_00
SEAT_ACCOUNTS = ("account-middlehand", "account-rearhand", "account-forehand")


A_RAMSCH = RamschPlayedOut(tricks=(), skat=())


def bock_table(
    triggers=(PASSED_IN,),
    *,
    rounds=(),
    series=None,
    game_list=(),
    overlap=BockOverlap.APPEND,
    occasion=None,
    ramsch_games=0,
):
    ramsch = (
        None
        if occasion is None
        else RamschSetting(
            occasion, RamschOptions(RamschScoring.POINTS, JungfrauRule.OFF, DurchmarschRule.WINS_120_FLAT)
        )
    )
    options = TableOptions(bock=BockOptions(frozenset(triggers), overlap), ramsch=ramsch)
    table = table_in(HandProgress(), options)
    return replace(table, bock=BockRounds(rounds, ramsch_games), series=series, game_list=game_list)


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


class TestARamschEnd:
    """The Ramsch is the hand all three passed: it uses up a Bock game and meets `passed-in`, with the total rule."""

    @pytest.mark.parametrize(
        ("triggers", "rounds", "series", "overlap", "expected"),
        [
            pytest.param((PASSED_IN,), (), None, BockOverlap.APPEND, (3,), id="starts-a-round"),
            pytest.param((PASSED_IN,), (2,), None, BockOverlap.APPEND, (1, 3), id="appends-after-the-pending-round"),
            pytest.param((PASSED_IN,), (2,), None, BockOverlap.MULTIPLY, (1, 3), id="starts-a-side-by-side-round"),
            pytest.param((PASSED_IN,), (2,), None, BockOverlap.IGNORE, (1,), id="starts-none-inside-a-round-at-ignore"),
            pytest.param((), (2,), None, BockOverlap.APPEND, (1,), id="passed-in-off-uses-the-game-up-only"),
            pytest.param((), (), None, BockOverlap.APPEND, (), id="passed-in-off-with-nothing-pending"),
            pytest.param(
                (PASSED_IN,), (2,), Series(6, 6), BockOverlap.APPEND, (), id="the-last-game-lets-rounds-lapse"
            ),
        ],
    )
    def test_it_uses_up_a_game_and_starts_a_round_only_when_passed_in_is_on(
        self, triggers, rounds, series, overlap, expected
    ):
        table = bock_table(triggers, rounds=rounds, series=series, overlap=overlap)

        assert bock_after(table, A_RAMSCH, a_ramsch_entry(seat_accounts=SEAT_ACCOUNTS)) == BockRounds(expected)

    @pytest.mark.parametrize(
        ("earlier", "scores", "rounds"),
        [
            pytest.param((), (-100, 0, 0), (3,), id="0-to-minus-100"),
            pytest.param((), (-47, 0, 0), (), id="0-to-minus-47"),
            pytest.param((entry(1, won=True, score=50),), (0, -47, 0), (), id="a-seat-the-ramsch-left-at-100"),
            pytest.param((entry(1, won=True, score=50),), (-100, 0, 0), (), id="a-seat-the-ramsch-took-from-100-to-0"),
        ],
    )
    def test_the_total_rule_reads_what_the_entry_changed(self, earlier, scores, rounds):
        table = bock_table((TOTAL_ENDING_IN_00,), game_list=earlier)

        assert bock_after(table, A_RAMSCH, a_ramsch_entry(scores, SEAT_ACCOUNTS)) == BockRounds(rounds)


ROUND_OCCASIONS = [RamschOccasion.BOCK_ROUNDS, RamschOccasion.PASSED_IN_AND_BOCK_ROUNDS]


class TestARamschRoundGameEnd:
    """No Bock game is pending and a Ramsch-round game is: the hand uses up a Ramsch-round game, never a Bock game."""

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    @pytest.mark.parametrize(
        ("triggers", "series", "expected"),
        [
            pytest.param((PASSED_IN,), None, BockRounds((), 1), id="nobody-passed-so-passed-in-does-not-fire"),
            pytest.param((), None, BockRounds((), 1), id="uses-the-game-up-only"),
            pytest.param((PASSED_IN,), Series(6, 6), BockRounds(()), id="the-last-game-lets-the-ramsch-games-lapse"),
        ],
    )
    def test_it_uses_up_a_ramsch_round_game(self, occasion, triggers, series, expected):
        table = bock_table(triggers, ramsch_games=2, series=series, occasion=occasion)

        assert bock_after(table, A_RAMSCH, a_ramsch_entry(seat_accounts=SEAT_ACCOUNTS)) == expected

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_the_total_rule_starts_a_bock_round_before_the_ramsch_games_still_pending(self, occasion):
        table = bock_table((TOTAL_ENDING_IN_00,), ramsch_games=2, occasion=occasion)

        assert bock_after(table, A_RAMSCH, a_ramsch_entry((-100, 0, 0), SEAT_ACCOUNTS)) == BockRounds((3,), 1)

    def test_a_three_pass_ramsch_outside_a_ramsch_round_meets_passed_in_as_at_a_table_with_the_third_pass_alone(self):
        table = bock_table(occasion=RamschOccasion.PASSED_IN_AND_BOCK_ROUNDS)

        assert bock_after(table, A_RAMSCH, a_ramsch_entry(seat_accounts=SEAT_ACCOUNTS)) == BockRounds((3,))


class TestTheEndOfABockRound:
    @pytest.mark.parametrize(
        ("occasion", "rounds", "ramsch_games", "expected"),
        [
            pytest.param(RamschOccasion.BOCK_ROUNDS, (1,), 0, BockRounds((), 3), id="rounds-only-adds-three"),
            pytest.param(
                RamschOccasion.PASSED_IN_AND_BOCK_ROUNDS,
                (1,),
                2,
                BockRounds((), 5),
                id="both-adds-three-to-the-pending",
            ),
            pytest.param(
                RamschOccasion.BOCK_ROUNDS, (2,), 0, BockRounds((1,), 0), id="a-game-before-the-end-adds-none"
            ),
            pytest.param(RamschOccasion.PASSED_IN, (1,), 0, BockRounds(()), id="the-third-pass-alone-adds-none"),
            pytest.param(None, (1,), 0, BockRounds(()), id="a-table-without-ramsch-adds-none"),
            pytest.param(
                RamschOccasion.BOCK_ROUNDS, (1, 3), 0, BockRounds((3,), 3), id="append-ends-the-first-round-only"
            ),
        ],
    )
    def test_it_adds_three_ramsch_round_games_only_at_a_table_that_plays_them(
        self, occasion, rounds, ramsch_games, expected
    ):
        table = bock_table((), rounds=rounds, ramsch_games=ramsch_games, occasion=occasion)

        assert bock_after(table, A_RAMSCH, a_ramsch_entry(seat_accounts=SEAT_ACCOUNTS)) == expected


class TestTheViewOfThePendingGames:
    def test_nothing_pending_is_no_game_left_and_factor_1(self):
        assert bock_view_of(bock_table()) == BockView(games_left=0, factor=1)

    @pytest.mark.parametrize(
        ("series", "running", "games_left"),
        [
            pytest.param(Series(6, 5), True, 2, id="the-running-game-counts"),
            pytest.param(Series(6, 6), True, 1, id="the-last-game-running"),
            pytest.param(Series(6, 2), False, 3, id="the-series-reaches-further-than-the-round"),
        ],
    )
    def test_it_never_counts_a_game_the_series_will_not_deal(self, series, running, games_left):
        table = bock_table(rounds=(3,), series=series)
        table = table if running else replace(table, hand=None)

        assert bock_view_of(table).games_left == games_left
