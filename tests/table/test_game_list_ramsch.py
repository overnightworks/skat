from dataclasses import replace

import pytest

from skat.engine.kontra import KontraReach
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import PushingRule
from skat.table.game_list import (
    RamschResultView,
    RamschSeatResult,
    RamschSeriesEntryView,
    RamschSeriesSeat,
    SeriesEntryView,
    result_view_of,
    series_list_view_of,
    standings_of,
    total_of,
)
from skat.table.records import HandProgress, RamschOccasion, RamschSetting, TableOptions
from skat.table.rules import result_pending
from tests.support.played_game import ANNA_BEN_CLEO, a_ramsch_entry, an_entry, table_in

REACH = KontraReach.KONTRA_RE
ANNA, BEN, CLEO = ANNA_BEN_CLEO
# Anna declares and wins 36 and the list's 50 on seat 1; the Ramsch then costs Anna 47 as seat 1.
DECLARED_THEN_RAMSCH = (an_entry(), a_ramsch_entry())


def standing_rows(game_list):
    return [(each.account_id, each.place, each.total, each.won, each.lost) for each in standings_of(game_list, REACH)]


class TestARamschInTheList:
    def test_totals_count_both_kinds_of_game(self):
        assert [total_of(DECLARED_THEN_RAMSCH, account, REACH) for account in ANNA_BEN_CLEO] == [86 - 47, 0, 0]

    def test_a_ramsch_scores_without_the_fifty_and_the_forty_whatever_the_kontra_reach(self):
        for reach in KontraReach:
            assert total_of((a_ramsch_entry((-47, 0, 0)),), ANNA, reach) == -47

    def test_standings_count_the_games_a_person_declared_only(self):
        assert standing_rows(DECLARED_THEN_RAMSCH) == [(ANNA, 1, 39, 1, 0), (BEN, 2, 0, 0, 0), (CLEO, 2, 0, 0, 0)]

    def test_a_ramsch_loss_is_no_lost_game_and_a_ramsch_alone_gives_no_game_to_anyone(self):
        assert standing_rows((a_ramsch_entry(),)) == [(BEN, 1, 0, 0, 0), (CLEO, 1, 0, 0, 0), (ANNA, 3, -47, 0, 0)]

    def test_a_chair_keeps_its_total_over_a_ramsch_played_on_another_chair(self):
        moved = a_ramsch_entry((0, 0, -30), (CLEO, BEN, ANNA))

        assert [total_of((moved,), account, REACH) for account in ANNA_BEN_CLEO] == [-30, 0, 0]


class TestTheRamschResult:
    def at_the_end(self, entry):
        table = table_in(HandProgress())
        return replace(table, hand=None, game_list=(an_entry(), entry))

    def test_names_every_seat_with_its_points_and_score_and_numbers_the_entry_by_its_place(self):
        view = result_view_of(self.at_the_end(a_ramsch_entry()))

        assert view == RamschResultView(
            ordinal=2,
            seats=(RamschSeatResult(1, 47, -47), RamschSeatResult(2, 40, 0), RamschSeatResult(3, 33, 0)),
            durchmarsch_seat=None,
            jungfrau=False,
            bock_factor=1,
            pushes=0,
            push_factor=1,
            divided_by_ten=False,
        )

    def test_stands_as_a_result_that_deals_the_next_hand(self):
        assert result_pending(self.at_the_end(a_ramsch_entry()))


class TestTheFactorsTheRamschResultDraws:
    @pytest.mark.parametrize(
        ("scoring", "durchmarsch", "swept", "push_factor", "divided_by_ten"),
        [
            pytest.param(RamschScoring.POINTS, DurchmarschRule.WINS_120, False, 4, False, id="points"),
            pytest.param(RamschScoring.POINTS_BY_TEN, DurchmarschRule.WINS_120, False, 4, True, id="points-by-ten"),
            pytest.param(
                RamschScoring.POINTS_BY_TEN, DurchmarschRule.WINS_120, True, 4, False, id="a-sweep-is-no-division"
            ),
            pytest.param(RamschScoring.POINTS, DurchmarschRule.WINS_120_FLAT, False, 4, False, id="a-loss-under-flat"),
            pytest.param(
                RamschScoring.POINTS, DurchmarschRule.WINS_120_FLAT, True, 1, False, id="a-flat-sweep-has-no-push"
            ),
        ],
    )
    def test_the_push_factor_is_the_one_the_scores_carry_and_the_division_is_named(
        self, scoring, durchmarsch, swept, push_factor, divided_by_ten
    ):
        options = TableOptions(
            ramsch=RamschSetting(
                RamschOccasion.PASSED_IN,
                RamschOptions(scoring, JungfrauRule.OFF, durchmarsch),
                pushing=PushingRule.JACKS_STAY,
            )
        )
        entry = replace(a_ramsch_entry(), pushes=2, durchmarsch_seat=1 if swept else None)
        table = replace(table_in(HandProgress(), options), hand=None, game_list=(entry,))

        view = result_view_of(table)

        assert (view.push_factor, view.divided_by_ten) == (push_factor, divided_by_ten)


class TestTheSeriesRows:
    def test_a_ramsch_row_names_each_seat_s_stored_name_and_score_and_a_declared_row_its_declarer(self):
        table = replace(table_in(HandProgress()), hand=None, game_list=DECLARED_THEN_RAMSCH)

        declared, ramsch = series_list_view_of(table)

        assert isinstance(declared, SeriesEntryView)
        assert ramsch == RamschSeriesEntryView(
            number=2,
            seats=(RamschSeriesSeat("Anna", -47), RamschSeriesSeat("Ben", 0), RamschSeriesSeat("Cleo", 0)),
            durchmarsch=False,
            jungfrau=False,
            bock_factor=1,
            pushes=0,
            push_factor=1,
        )

    @pytest.mark.parametrize(("durchmarsch_seat", "jungfrau"), [(None, True), (2, False)])
    def test_a_row_says_whether_a_durchmarsch_or_a_jungfrau_made_it(self, durchmarsch_seat, jungfrau):
        entry = replace(a_ramsch_entry(), durchmarsch_seat=durchmarsch_seat, jungfrau=jungfrau)
        table = replace(table_in(HandProgress()), hand=None, game_list=(entry,))

        (row,) = series_list_view_of(table)

        assert (row.durchmarsch, row.jungfrau) == (durchmarsch_seat is not None, jungfrau)
