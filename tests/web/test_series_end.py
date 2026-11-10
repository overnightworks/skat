from contextlib import nullcontext
from dataclasses import replace

import pytest

from skat.table.records import EndProposal, Refusal, Series, TableId
from skat.table.service import TableService
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.web.support.playing import Table
from tests.web.support.series import (
    agree_to_end,
    deal_next,
    headers_of,
    play_a_series,
    refuse_to_end,
    tap_new_series,
    tap_weiter,
)

SERIES_LENGTH = 12


def proposal_of(answer):
    return answer.json()["series"]["end_proposal"]


def accounts_of(table):
    return [chair.occupant.account_id for chair in table.record.chairs]


def yes(skat, table, seat, command_id=None):
    return agree_to_end(
        skat, headers_of(table)[seat - 1], table.table_id, command_id or f"command-yes-{seat}-{table.record.version}"
    )


def no(skat, table, seat, command_id=None):
    return refuse_to_end(
        skat, headers_of(table)[seat - 1], table.table_id, command_id or f"command-no-{seat}-{table.record.version}"
    )


def end_early(skat, table):
    for seat in (1, 2, 3):
        assert yes(skat, table, seat).status_code == 200


def entries_of(skat, table):
    skat.client.cookies.clear()
    return skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher).json()[
        "entries"
    ]


@pytest.fixture
def mid_series(skat):
    """A series of twelve stopped at its second game's pending result."""
    table, _ = play_a_series(skat, SERIES_LENGTH, games_to_play=2)
    return table


@pytest.fixture
def after_a_passed_in_hand(skat):
    """A series of twelve whose second hand was passed in: the pause before the next deal."""
    table, _ = play_a_series(skat, SERIES_LENGTH, passed_in_hand=2, games_to_play=2)
    return table


class TestTheProposal:
    def test_the_first_yes_proposes_and_every_viewer_reads_the_proposers_seat(self, skat, mid_series):
        table = mid_series
        before = table.read_as(table.watcher).json()

        answer = yes(skat, table, 1)

        assert answer.status_code == 200
        for headers in (*headers_of(table), table.watcher):
            seen = table.read_as(headers).json()["series"]
            assert seen["end_proposal"] == {"proposer_seat": 1, "accepter_seat": None}
            assert (seen["over"], seen["standings"]) == (False, None)
        assert table.read_as(table.watcher).json()["result"] == before["result"]

    def test_the_second_yes_accepts_and_the_series_goes_on(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)

        answer = yes(skat, table, 2)

        assert proposal_of(answer) == {"proposer_seat": 1, "accepter_seat": 2}
        assert answer.json()["series"]["over"] is False

    def test_the_third_yes_ends_the_series_at_once_with_the_games_so_far(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        answer = yes(skat, table, 3)

        series = answer.json()["series"]
        assert (series["game_number"], series["game_count"], series["over"]) == (2, SERIES_LENGTH, True)
        assert series["end_proposal"] is None
        assert [each["place"] for each in series["standings"]] == sorted(each["place"] for each in series["standings"])
        assert len(series["standings"]) == 3
        assert answer.json()["result"]["ordinal"] == 2
        assert answer.json()["hand"] is None
        assert not deal_next(skat, table.table_id, accounts_of(table))
        assert len(entries_of(skat, table)) == 2

    def test_a_series_whose_games_were_all_passed_in_ends_with_no_standings(self, skat):
        table, _ = play_a_series(skat, SERIES_LENGTH, passed_in_hand=1, games_to_play=1)
        yes(skat, table, 1)
        yes(skat, table, 2)

        answer = yes(skat, table, 3)

        assert (answer.json()["series"]["over"], answer.json()["series"]["standings"]) == (True, [])

    def test_the_end_clears_every_weiter_mark_and_nothing_deals(self, skat, mid_series):
        table = mid_series
        for seat in (2, 3):
            assert tap_weiter(skat, headers_of(table)[seat - 1], table.table_id, f"weiter-{seat}", 2).status_code == 200
        yes(skat, table, 1)
        yes(skat, table, 2)

        yes(skat, table, 3)

        assert [chair.ready for chair in table.record.chairs] == [False, False, False]
        assert not deal_next(skat, table.table_id, accounts_of(table))

    def test_weiter_after_the_early_end_is_refused_as_at_a_regular_end(self, skat, mid_series):
        table = mid_series
        end_early(skat, table)
        before = table.record

        answer = tap_weiter(skat, headers_of(table)[0], table.table_id, "weiter-late", 2)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.SERIES_OVER)
        assert table.record == before

    def test_all_three_tapping_new_series_after_the_early_end_start_the_next_series(self, skat, mid_series):
        table = mid_series
        end_early(skat, table)
        for number, headers in enumerate(headers_of(table), start=1):
            assert tap_new_series(skat, headers, table.table_id, f"command-new-{number}").status_code == 200

        assert deal_next(skat, table.table_id, accounts_of(table))

        series = table.read_as(table.watcher).json()["series"]
        assert (series["game_number"], series["over"], series["end_proposal"]) == (1, False, None)
        assert table.record.series == Series(SERIES_LENGTH, 1)
        assert entries_of(skat, table) == []

    def test_a_viewer_sees_the_same_series_with_seats_only_during_a_proposal_and_after_the_end(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        during = [table.read_as(each).json()["series"] for each in (*headers_of(table), table.watcher)]
        assert all(view == during[0] for view in during)
        assert set(during[0]["end_proposal"]) == {"proposer_seat", "accepter_seat"}
        assert len(entries_of(skat, table)) == 2

        assert yes(skat, table, 3).status_code == 200

        after = [table.read_as(each).json()["series"] for each in (*headers_of(table), table.watcher)]
        assert all(view == after[0] for view in after)
        assert len(entries_of(skat, table)) == 2


class TestTheNo:
    @pytest.mark.parametrize("refuser", [1, 2, 3], ids=["the-proposer", "an-accepter", "the-other"])
    def test_any_seated_no_clears_the_proposal_and_the_series_plays_on(self, skat, mid_series, refuser):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        answer = no(skat, table, refuser)

        assert (answer.status_code, proposal_of(answer), answer.json()["series"]["over"]) == (200, None, False)

    def test_a_no_with_no_proposal_is_refused(self, skat, mid_series):
        table = mid_series
        before = table.record

        answer = no(skat, table, 1)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NO_PROPOSAL)
        assert table.record == before

    def test_a_watcher_cannot_say_no(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)

        answer = refuse_to_end(skat, table.watcher, table.table_id, "no-watcher")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NOT_SEATED)
        assert table.record.series.end_proposal == EndProposal(1)

    def test_a_yes_after_a_no_proposes_anew_by_its_sender(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)
        no(skat, table, 1)

        answer = yes(skat, table, 3)

        assert proposal_of(answer) == {"proposer_seat": 3, "accepter_seat": None}

    def test_a_no_after_the_end_finds_no_proposal(self, skat, mid_series):
        table = mid_series
        end_early(skat, table)

        answer = no(skat, table, 1)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NO_PROPOSAL)
        assert table.record.series.ended_early


class TestTheNextDeal:
    def test_the_next_hand_clears_the_proposal(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        for seat in (1, 2, 3):
            tap_weiter(skat, headers_of(table)[seat - 1], table.table_id, f"weiter-{seat}", 2)

        assert deal_next(skat, table.table_id, accounts_of(table))

        series = table.read_as(table.watcher).json()["series"]
        assert (series["game_number"], series["end_proposal"]) == (3, None)

    def test_a_proposal_after_a_passed_in_hand_is_accepted_and_the_pauses_deal_clears_it(
        self, skat, after_a_passed_in_hand
    ):
        table = after_a_passed_in_hand
        yes(skat, table, 1)
        assert proposal_of(yes(skat, table, 2)) == {"proposer_seat": 1, "accepter_seat": 2}

        assert deal_next(skat, table.table_id, accounts_of(table))

        assert table.record.series == Series(SERIES_LENGTH, 3)

    def test_an_early_end_during_the_pause_deals_nothing(self, skat, after_a_passed_in_hand):
        table = after_a_passed_in_hand
        end_early(skat, table)

        assert not deal_next(skat, table.table_id, accounts_of(table))

        assert table.read_as(table.watcher).json()["series"]["over"] is True


class TestChairsChangingHands:
    def test_the_proposers_stand_up_clears_the_proposal(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)

        assert skat.stand(headers_of(table)[0], table.table_id, command_id="stand-anna").status_code == 200

        assert table.record.series.end_proposal is None

    def test_an_accepter_who_stands_up_takes_only_the_acceptance_and_the_newcomer_answers_like_the_others(
        self, skat, mid_series
    ):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)
        skat.stand(headers_of(table)[1], table.table_id, command_id="stand-ben")
        assert table.record.series.end_proposal == EndProposal(1)
        assert skat.sit(table.watcher, table.table_id, 2, command_id="sit-dora").status_code == 200

        assert proposal_of(yes(skat, table, 3)) == {"proposer_seat": 1, "accepter_seat": 3}
        ended = agree_to_end(skat, table.watcher, table.table_id, "yes-dora")

        assert ended.json()["series"]["over"] is True

    @pytest.mark.parametrize(
        ("leaver", "left"),
        [(1, None), (2, EndProposal(1)), (3, EndProposal(1, 2))],
        ids=["the-proposers-hold", "an-accepters-hold", "anyone-elses-hold"],
    )
    def test_an_away_hold_that_frees_a_chair_takes_only_its_holders_part(self, skat, mid_series, leaver, left):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        freed = TableService(skat.store).free_chair(
            TableId(table.table_id), accounts_of(table)[leaver - 1], nullcontext(True)
        )

        assert freed is True
        assert table.record.series.end_proposal == left

    def test_a_sitter_after_the_early_end_is_not_ready_and_the_sit_that_fills_the_last_chair_deals_nothing(
        self, skat, mid_series
    ):
        table = mid_series
        end_early(skat, table)
        skat.stand(headers_of(table)[0], table.table_id, command_id="stand-anna")

        assert skat.sit(table.watcher, table.table_id, 1, command_id="sit-dora").status_code == 200

        assert [chair.ready for chair in table.record.chairs] == [False, False, False]
        assert table.record.hand is None


class TestRefusals:
    def test_a_yes_during_a_hand_is_refused(self, skat):
        table = Table(skat)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(SERIES_LENGTH, 1))
        before = table.record

        answer = agree_to_end(skat, headers_of(table)[0], table.table_id, "yes-running")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.HAND_RUNNING)
        assert table.record == before

    def test_a_yes_before_the_first_deal_is_refused(self, skat):
        table = Table(skat)
        skat.store.tables[table.table_id] = replace(
            table.record, hand=None, dealer=None, series=Series(SERIES_LENGTH, 0)
        )

        answer = agree_to_end(skat, headers_of(table)[0], table.table_id, "yes-early")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NO_GAME_YET)

    def test_a_yes_at_a_regular_end_is_refused(self, skat):
        table, _ = play_a_series(skat)
        before = table.record

        answer = agree_to_end(skat, headers_of(table)[0], table.table_id, "command-yes-end")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.SERIES_OVER)
        assert table.record == before

    def test_a_yes_at_a_table_without_a_series_is_refused(self, skat):
        table = Table(skat)
        skat.store.tables[table.table_id] = replace(table.record, series=None)

        answer = agree_to_end(skat, headers_of(table)[0], table.table_id, "yes-plain")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NO_SERIES)

    def test_a_watcher_cannot_say_yes(self, skat, mid_series):
        table = mid_series
        before = table.record

        answer = agree_to_end(skat, table.watcher, table.table_id, "yes-watcher")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NOT_SEATED)
        assert table.record == before


class TestRetries:
    def test_a_yes_from_a_seat_that_already_said_yes_changes_nothing_and_adds_no_version(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)
        before = table.record

        assert yes(skat, table, 1, "yes-again-1").status_code == 200
        assert yes(skat, table, 2, "yes-again-2").status_code == 200

        assert table.record == before

    def test_a_retried_step_replays_its_answer_also_after_the_end_and_after_the_next_deal(self, skat, mid_series):
        table = mid_series
        first = yes(skat, table, 1, "yes-anna")
        yes(skat, table, 2)
        end_early(skat, table)
        ended = table.record

        assert yes(skat, table, 1, "yes-anna").status_code == first.status_code == 200
        assert table.record == ended
        for number, headers in enumerate(headers_of(table), start=1):
            tap_new_series(skat, headers, table.table_id, f"command-new-{number}")
        deal_next(skat, table.table_id, accounts_of(table))
        dealt = table.record

        assert yes(skat, table, 1, "yes-anna").status_code == 200
        assert table.record == dealt

    def test_a_retried_no_replays_its_answer(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        first = no(skat, table, 2, "command-no-ben")
        version = table.record.version

        assert no(skat, table, 2, "command-no-ben").json() == first.json()
        assert table.record.version == version

    def test_a_command_id_reused_across_the_two_routes_or_on_weiter_is_refused(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1, "shared-id")

        for answer in (
            refuse_to_end(skat, headers_of(table)[0], table.table_id, "shared-id"),
            tap_weiter(skat, headers_of(table)[0], table.table_id, "shared-id", 2),
        ):
            assert answer.status_code == 409
            assert "reused" in answer.json()["detail"]
