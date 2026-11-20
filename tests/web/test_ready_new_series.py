from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skat.engine.deal import next_dealer
from skat.table.records import Ending, Refusal, TableId
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, with_known_deal
from tests.support.played_game import a_whole_game
from tests.web.support.series import (
    change_next_settings,
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

        answer = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-late", series=2)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.SERIES_NOT_OVER)
        assert table.record == before

    @pytest.mark.parametrize("series", [2, 3], ids=["a-series-not-yet-started", "a-series-further-on"])
    def test_a_tap_naming_another_series_is_refused_and_changes_nothing(self, skat, ended, series):
        table, _ = ended
        before = table.record

        answer = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-stale", series=series)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.STALE_SERIES)
        assert table.record == before

    def test_taps_naming_the_next_series_delete_nothing_and_deal_nothing(self, skat, ended):
        table, _ = ended
        for number, headers in enumerate(headers_of(table), start=1):
            assert tap_new_series(skat, headers, table.table_id, f"tap-stale-{number}", series=2).status_code == 409

        assert not deal_the_next_series(skat, table)

        assert len(entries_of(skat, table)) == 3
        assert [chair.ready for chair in table.record.chairs] == [False, False, False]

    def test_a_tap_naming_the_series_that_was_deleted_changes_nothing_in_the_next_one(self, skat, ended):
        table, _ = ended
        all_tap(skat, table)
        assert deal_the_next_series(skat, table)
        before = table.record

        answer = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-older-series", series=1)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.STALE_SERIES)
        assert table.record == before

    def test_a_retry_of_a_stale_tap_replays_the_refusal(self, skat, ended):
        table, _ = ended
        first = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-stale", series=2)

        again = tap_new_series(skat, headers_of(table)[0], table.table_id, "tap-stale", series=2)

        assert (again.status_code, again.json()["reason"]) == (first.status_code, Refusal.STALE_SERIES)

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
            "number": 2,
            "game_number": 1,
            "game_count": 3,
            "over": False,
            "standings": None,
            "end_proposal": None,
            "end_refused_seats": [],
            "new_series_answer_by": None,
            "next_settings": None,
        }
        assert (seen["result"], marks(table.read_as(table.watcher))) == (None, [False, False, False])
        assert seen["hand"] is not None
        assert [chair["total"] for chair in seen["chairs"]] == [0, 0, 0]
        assert table.record.dealer == next_dealer(old_dealer)
        assert entries_of(skat, table) == []

    def test_the_third_tap_shows_the_old_totals_and_every_viewer_reads_zero_after_the_deal(self, skat, ended):
        table, _ = ended
        old_totals = [chair["total"] for chair in table.read_as(table.watcher).json()["chairs"]]

        answer = all_tap(skat, table)
        assert [chair["total"] for chair in answer.json()["chairs"]] == old_totals
        assert deal_the_next_series(skat, table)

        for viewer in (*headers_of(table), table.watcher):
            assert [chair["total"] for chair in table.read_as(viewer).json()["chairs"]] == [0, 0, 0]

    def test_the_new_series_first_result_gives_each_chair_that_games_gain_only(self, skat, ended):
        table, _ = ended
        all_tap(skat, table)
        assert deal_the_next_series(skat, table)
        with_known_deal(skat, table.table_id)
        table.declared_hand_game()
        table.played_out(each.card for each in a_whole_game(table.record))

        seen = table.read_as(table.watcher).json()

        gains = {each["seat"]: each["gain"] for each in seen["result"]["gains"]}
        assert [chair["total"] for chair in seen["chairs"]] == [gains[chair["seat"]] for chair in seen["chairs"]]

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


KONTRA = {"sayer": "bidders-only", "reach": "up-to-hirsch", "deadline": "own-card"}


def next_settings_of_view(view):
    return view["series"]["next_settings"]


def next_settings_of(answer):
    return next_settings_of_view(answer.json())


class TestTheNextSettings:
    def test_the_next_series_line_reads_the_last_series_until_a_save(self, skat, ended):
        table, _ = ended

        seen = table.read_as(table.watcher)

        assert next_settings_of(seen) == {
            "game_count": 3,
            "options": table.read_as(table.watcher).json()["options"],
            "revision": 0,
        }

    def test_a_seated_member_saves_and_every_viewer_reads_the_new_line(self, skat, ended):
        table, _ = ended

        saved = change_next_settings(
            skat, headers_of(table)[1], table.table_id, "save-first", series_length=12, options={"kontra": KONTRA}
        )

        assert saved.status_code == 200, saved.text
        for viewer in (*headers_of(table), table.watcher):
            line = next_settings_of(table.read_as(viewer))
            assert (line["game_count"], line["revision"], line["options"]["kontra"]) == (12, 1, KONTRA)

    def test_every_open_stream_shows_the_saved_line_at_once(self, skat, ended):
        table, _ = ended
        people = [(headers, None) for headers in (*headers_of(table), table.watcher)]

        with streams_of(skat, table.table_id, people) as streams:
            saved = change_next_settings(skat, headers_of(table)[0], table.table_id, "save-first", series_length=9)
            assert saved.status_code == 200, saved.text

            seen = [next(messages) for messages in streams]

        assert [next_settings_of_view(view)["game_count"] for view in seen] == [9] * 4

    def test_a_save_leaves_the_series_that_ended_as_it_was(self, skat, ended):
        table, _ = ended
        before = table.read_as(table.watcher).json()

        change_next_settings(skat, headers_of(table)[0], table.table_id, "save-first", series_length=12)

        seen = table.read_as(table.watcher).json()
        assert (seen["series"]["game_count"], seen["options"]) == (3, before["options"])

    def test_a_save_takes_back_every_seats_new_series(self, skat, ended):
        table, _ = ended
        first, second, _ = headers_of(table)
        tap_new_series(skat, first, table.table_id, "tap-new-1")
        tap_new_series(skat, second, table.table_id, "tap-new-2")

        saved = change_next_settings(skat, first, table.table_id, "save-first", series_length=12)

        assert (marks(saved), saved.json()["series"]["new_series_answer_by"]) == ([False, False, False], None)

    def test_a_watcher_is_refused_and_nothing_changes(self, skat, ended):
        table, _ = ended
        before = table.record

        refused = change_next_settings(skat, table.watcher, table.table_id, "save-watcher", series_length=12)

        assert (refused.status_code, refused.json()["reason"]) == (409, Refusal.NOT_SEATED)
        assert table.record == before

    def test_a_tap_on_older_settings_is_refused_and_a_tap_on_the_saved_ones_accepted(self, skat, ended):
        table, _ = ended
        first, second, _ = headers_of(table)
        change_next_settings(skat, first, table.table_id, "save-first", series_length=12)

        stale = tap_new_series(skat, second, table.table_id, "tap-stale", settings=0)
        fresh = tap_new_series(skat, second, table.table_id, "tap-fresh", settings=1)

        assert (stale.status_code, stale.json()["reason"]) == (409, Refusal.STALE_SETTINGS)
        assert (fresh.status_code, marks(fresh)) == (200, [False, True, False])

    def test_a_save_on_older_settings_is_refused_and_a_save_on_the_saved_ones_accepted(self, skat, ended):
        table, _ = ended
        first, second, _ = headers_of(table)
        change_next_settings(skat, first, table.table_id, "save-first", series_length=12)

        stale = change_next_settings(skat, second, table.table_id, "save-stale", series_length=15, revision=0)
        fresh = change_next_settings(skat, second, table.table_id, "save-fresh", series_length=15, revision=1)

        assert (stale.status_code, stale.json()["reason"]) == (409, Refusal.STALE_SETTINGS)
        assert (fresh.status_code, fresh.json()["series"]["next_settings"]["game_count"]) == (200, 15)

    def test_a_tap_naming_no_settings_is_accepted_on_unsaved_settings_and_refused_after_a_save(self, skat, ended):
        table, _ = ended
        first, second, _ = headers_of(table)

        unsaved = tap_new_series(skat, first, table.table_id, "tap-unsaved", settings=None)
        change_next_settings(skat, first, table.table_id, "save-first", series_length=12)
        saved = tap_new_series(skat, second, table.table_id, "tap-saved", settings=None)

        assert unsaved.status_code == 200
        assert (saved.status_code, saved.json()["reason"]) == (409, Refusal.STALE_SETTINGS)

    def test_the_next_series_is_dealt_with_the_saved_length_and_rules(self, skat, ended):
        table, _ = ended
        change_next_settings(
            skat, headers_of(table)[0], table.table_id, "save-first", series_length=12, options={"kontra": KONTRA}
        )
        for number, headers in enumerate(headers_of(table), start=1):
            assert tap_new_series(skat, headers, table.table_id, f"tap-new-{number}", settings=1).status_code == 200

        assert deal_the_next_series(skat, table)

        seen = table.read_as(table.watcher).json()
        assert (seen["series"]["game_count"], seen["options"]["kontra"], seen["series"]["next_settings"]) == (
            12,
            KONTRA,
            None,
        )

    @pytest.mark.parametrize("length", [0, 2, 4, 100, "12", 12.5], ids=str)
    def test_a_length_the_opening_sheet_refuses_is_refused(self, skat, ended, length):
        table, _ = ended
        before = table.record

        refused = change_next_settings(skat, headers_of(table)[0], table.table_id, "save-bad", series_length=length)

        assert refused.status_code == 422
        assert table.record == before

    def test_options_the_opening_sheet_refuses_are_refused(self, skat, ended):
        table, _ = ended
        ramsch_after_bock = {
            "occasion": "bock-rounds",
            "scoring": "points",
            "jungfrau": "doubled",
            "durchmarsch": "wins-120",
        }

        refused = change_next_settings(
            skat,
            headers_of(table)[0],
            table.table_id,
            "save-bad",
            series_length=12,
            options={"ramsch": ramsch_after_bock},
        )

        assert refused.status_code == 422

    def test_a_save_before_the_series_is_over_is_refused(self, skat):
        table, _ = play_a_series(skat)
        all_tap(skat, table)
        assert deal_the_next_series(skat, table)

        refused = change_next_settings(
            skat, headers_of(table)[0], table.table_id, "save-late", series=2, series_length=12
        )

        assert (refused.status_code, refused.json()["reason"]) == (409, Refusal.SERIES_NOT_OVER)

    def test_a_save_naming_another_series_is_stale(self, skat, ended):
        table, _ = ended

        refused = change_next_settings(
            skat, headers_of(table)[0], table.table_id, "save-stale", series=2, series_length=12
        )

        assert (refused.status_code, refused.json()["reason"]) == (409, Refusal.STALE_SERIES)

    def test_a_save_at_a_table_that_ended_finds_no_table(self, skat, ended):
        table, _ = ended
        with skat.store.begin() as transaction:
            transaction.end_table(TableId(table.table_id), datetime.now(UTC), Ending.stopped())

        gone = change_next_settings(skat, headers_of(table)[1], table.table_id, "save-late", series_length=12)

        assert gone.status_code == 404

    def test_a_retried_save_answers_the_first_outcome_and_counts_one_revision(self, skat, ended):
        table, _ = ended
        first = change_next_settings(skat, headers_of(table)[0], table.table_id, "save-first", series_length=12)

        again = change_next_settings(skat, headers_of(table)[0], table.table_id, "save-first", series_length=12)

        assert (again.status_code, next_settings_of(again)) == (200, next_settings_of(first))
        assert next_settings_of(again)["revision"] == 1

    def test_a_command_id_reused_for_other_settings_is_refused(self, skat, ended):
        table, _ = ended
        change_next_settings(skat, headers_of(table)[0], table.table_id, "save-first", series_length=12)

        answer = change_next_settings(skat, headers_of(table)[0], table.table_id, "save-first", series_length=15)

        assert answer.status_code == 409
        assert "reused" in answer.json()["detail"]


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
