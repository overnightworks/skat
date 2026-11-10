from dataclasses import replace

import pytest

from skat.engine.deal import next_dealer
from skat.table.records import Refusal
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, with_known_deal
from tests.support.played_game import a_whole_game
from tests.web.support.series import (
    deal_next,
    headers_of,
    play_a_series,
    play_the_dealt_series,
    tap_new_series,
    tap_weiter,
)
from tests.web.support.skat import streams_of


def marks(answer):
    return [chair["ready"] for chair in answer.json()["chairs"]]


def entries_of(skat, table):
    skat.client.cookies.clear()
    answer = skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
    assert answer.status_code == 200, answer.text
    return answer.json()["entries"]


def deal_the_next_series(skat, table, accounts=None):
    """Deal with `accounts` connected, by default the three who sit."""
    if accounts is None:
        accounts = [chair.occupant.account_id for chair in table.record.chairs]
    return deal_next(skat, table.table_id, accounts)


def all_tap(skat, table, prefix="tap-new"):
    for number, headers in enumerate(headers_of(table), start=1):
        answer = tap_new_series(skat, headers, table.table_id, f"{prefix}-{number}")
        assert answer.status_code == 200, answer.text
    return answer


@pytest.fixture
def ended(skat):
    """A series of three played to its end, and the display names of the three who played it."""
    return play_a_series(skat)


class TestTheTaps:
    def test_two_taps_mark_two_chairs_and_the_standings_and_the_last_result_stand(self, skat, ended):
        table, _ = ended
        first, second, _ = headers_of(table)

        tap_new_series(skat, first, table.table_id, "tap-new-1")
        answer = tap_new_series(skat, second, table.table_id, "tap-new-2")

        assert answer.status_code == 200
        assert marks(answer) == [True, True, False]
        assert (answer.json()["series"]["over"], answer.json()["result"]["ordinal"]) == (True, 3)
        assert answer.json()["series"]["standings"]
        assert table.record.hand is None
        assert not deal_the_next_series(skat, table)
        assert len(entries_of(skat, table)) == 3

    def test_the_same_chair_tapping_again_changes_nothing_and_adds_no_version(self, skat, ended):
        table, _ = ended
        headers = headers_of(table)[0]
        tap_new_series(skat, headers, table.table_id, "tap-new-1")
        before = table.record

        again = tap_new_series(skat, headers, table.table_id, "tap-again")

        assert again.status_code == 200
        assert table.record == before

    def test_a_watcher_sees_the_marks_and_the_standings_and_cannot_tap(self, skat, ended):
        table, _ = ended
        tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-new-1")
        before = table.record

        refused = tap_new_series(skat, table.watcher, table.table_id, "tap-watcher")
        seen = table.read_as(table.watcher)

        assert (refused.status_code, refused.json()["reason"]) == (409, Refusal.NOT_SEATED)
        assert marks(seen) == [True, False, False]
        assert seen.json()["series"]["standings"]
        assert table.record == before

    def test_a_tap_while_a_hand_runs_says_the_series_is_not_over_and_changes_nothing(self, skat, ended):
        table, _ = ended
        all_tap(skat, table)
        assert deal_the_next_series(skat, table)
        before = table.record

        answer = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-late")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.SERIES_NOT_OVER)
        assert table.record == before

    def test_a_tap_at_a_table_without_a_series_says_so_and_changes_nothing(self, skat, ended):
        table, _ = ended
        skat.store.tables[table.table_id] = replace(table.record, series=None)
        before = table.record

        answer = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-none")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NO_SERIES)
        assert table.record == before

    def test_weiter_at_the_end_marks_no_chair_before_and_after_a_new_series_tap(self, skat, ended):
        table, _ = ended
        first = headers_of(table)[0]

        before = tap_weiter(skat, first, table.table_id, "weiter-before", ordinal=3)
        tap_new_series(skat, first, table.table_id, "tap-new-1")
        after = tap_weiter(skat, headers_of(table)[1], table.table_id, "weiter-after", ordinal=3)

        assert [each.json()["reason"] for each in (before, after)] == [Refusal.SERIES_OVER] * 2
        assert [chair.ready for chair in table.record.chairs] == [True, False, False]

    def test_the_mark_leaves_with_whoever_stands_up_and_the_newcomers_tap_completes_the_three(self, skat, ended):
        table, _ = ended
        first, second, third = headers_of(table)
        tap_new_series(skat, first, table.table_id, "tap-new-1")
        assert skat.stand(first, table.table_id, command_id="stand-anna").status_code == 200
        assert [chair.ready for chair in table.record.chairs] == [False, False, False]

        assert skat.sit(table.watcher, table.table_id, 1, command_id="sit-dora").status_code == 200
        for number, headers in enumerate((table.watcher, second, third), start=1):
            assert tap_new_series(skat, headers, table.table_id, f"tap-new-{number}").status_code == 200

        assert [chair.ready for chair in table.record.chairs] == [True, True, True]


class TestTheNextSeries:
    def test_the_third_tap_still_shows_the_end_and_the_next_deal_starts_game_one_with_an_empty_list(self, skat, ended):
        table, _ = ended
        old_dealer = table.record.dealer

        answer = all_tap(skat, table)

        assert (answer.json()["series"]["over"], marks(answer)) == (True, [True, True, True])
        assert deal_the_next_series(skat, table)
        seen = table.read_as(table.watcher).json()
        assert seen["series"] == {
            "game_number": 1,
            "game_count": 3,
            "over": False,
            "standings": None,
            "end_proposal": None,
        }
        assert (seen["result"], marks(table.read_as(table.watcher))) == (None, [False, False, False])
        assert seen["hand"] is not None
        assert [chair["total"] for chair in seen["chairs"]] == [None] * 3
        assert table.record.dealer == next_dealer(old_dealer)
        assert entries_of(skat, table) == []

    def test_a_series_ended_by_a_passed_in_last_game_starts_the_next_the_same_way(self, skat):
        table, _ = play_a_series(skat, passed_in_hand=3)

        all_tap(skat, table)

        assert deal_the_next_series(skat, table)
        assert table.read_as(table.watcher).json()["series"]["game_number"] == 1
        assert entries_of(skat, table) == []

    def test_one_member_away_deals_nothing_until_all_three_are_connected(self, skat, ended):
        table, _ = ended
        all_tap(skat, table)
        accounts = [chair.occupant.account_id for chair in table.record.chairs]

        assert not deal_the_next_series(skat, table, accounts[:2])
        assert len(table.record.game_list) == 3
        assert deal_the_next_series(skat, table, accounts)

    def test_the_third_tap_deals_once_all_three_streams_are_open(self, server):
        table, _ = play_a_series(server)
        people = [(headers, None) for headers in headers_of(table)]

        with streams_of(server, table.table_id, people):
            all_tap(server, table)

        seen = table.read_as(table.watcher).json()
        assert (seen["series"]["game_number"], seen["series"]["over"]) == (1, False)
        assert entries_of(server, table) == []

    def test_the_next_series_played_to_its_end_ranks_only_its_own_games(self, skat):
        table, names = play_a_series(skat, swap_after_first=2)
        newcomer = table.record.chairs[1].occupant.display_name
        all_tap(skat, table)
        assert deal_the_next_series(skat, table)
        with_known_deal(skat, table.table_id)

        play_the_dealt_series(skat, table, 3, number=2)

        seen = table.read_as(table.watcher).json()
        standings = seen["series"]["standings"]
        assert seen["series"]["over"] is True
        assert {each["display_name"] for each in standings} == {names[0], newcomer, names[2]}
        assert sum(each["won"] + each["lost"] for each in standings) == 3
        assert len(entries_of(skat, table)) == 3

    def test_no_answer_carries_a_card_of_another_or_an_account_id(self, skat, ended):
        table, _ = ended
        accounts = {chair.occupant.account_id for chair in table.record.chairs}
        all_tap(skat, table)
        deal_the_next_series(skat, table)

        seen = table.read_as(table.watcher)

        assert cards_in(seen.json()) == set()
        assert not any(account in seen.text for account in accounts)


class TestARetry:
    def test_each_tap_retried_before_and_after_the_deal_returns_the_current_table_and_changes_nothing(
        self, skat, ended
    ):
        table, _ = ended
        taps = list(enumerate(headers_of(table), start=1))
        for number, headers in taps:
            tap_new_series(skat, headers, table.table_id, f"tap-new-{number}")
        before_the_deal = table.record
        for number, headers in taps:
            assert tap_new_series(skat, headers, table.table_id, f"tap-new-{number}").status_code == 200
        assert table.record == before_the_deal

        assert deal_the_next_series(skat, table)
        dealt = table.record
        for number, headers in taps:
            assert tap_new_series(skat, headers, table.table_id, f"tap-new-{number}").status_code == 200

        assert table.record == dealt
        assert dealt.series.deals == 1
        assert entries_of(skat, table) == []

        with_known_deal(skat, table.table_id)
        table.declared_hand_game()
        table.played_out(each.card for each in a_whole_game(table.record))
        played = table.record
        for number, headers in taps:
            assert tap_new_series(skat, headers, table.table_id, f"tap-new-{number}").status_code == 200

        assert table.record == played
        assert len(entries_of(skat, table)) == 1

    def test_a_refused_tap_retried_replays_its_refusal_after_the_next_series_began(self, skat, ended):
        table, _ = ended
        refused = tap_new_series(skat, table.watcher, table.table_id, "tap-watcher")
        all_tap(skat, table)
        deal_the_next_series(skat, table)

        again = tap_new_series(skat, table.watcher, table.table_id, "tap-watcher")

        assert (refused.status_code, again.status_code) == (409, 409)
        assert again.json()["reason"] == Refusal.NOT_SEATED

    def test_the_command_id_of_a_tap_reused_for_weiter_is_refused(self, skat, ended):
        table, _ = ended
        headers = headers_of(table)[0]
        tap_new_series(skat, headers, table.table_id, "shared-id")

        answer = tap_weiter(skat, headers, table.table_id, "shared-id", ordinal=3)

        assert answer.status_code == 409
        assert "reused" in answer.json()["detail"]
