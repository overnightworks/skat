import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.host.app import END_ANSWER_RECOVERY_SECONDS, ServerRounds
from skat.table.ready import NewSeriesCommand
from skat.table.records import Actor, EndReason, Refusal, Series, TableId, TableRecord
from skat.table.series_end import END_ANSWER_SECONDS, SeriesEndCommand
from skat.table.service import TableService
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.settings import DEFAULT_STREAMS_PER_ACCOUNT
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
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
from tests.web.support.skat import FakeTime, Skat

SERIES_LENGTH = 12


def proposal_of(answer):
    """The proposal an answer reads, without the instant its minute ends at."""
    proposal = answer.json()["series"]["end_proposal"]
    return None if proposal is None else {key: value for key, value in proposal.items() if key != "answer_by"}


def series_of(table):
    return table.read_as(table.watcher).json()["series"]


def standing_of(table):
    """The proposer and the yeses of the proposal the table stores."""
    proposal = table.record.series.end_proposal
    return None if proposal is None else (proposal.proposer, proposal.agreed)


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
            assert {key: seen["end_proposal"][key] for key in ("proposer_seat", "agreed_seats")} == {
                "proposer_seat": 1,
                "agreed_seats": [1],
            }
            assert (seen["over"], seen["standings"]) == (False, None)
        assert table.read_as(table.watcher).json()["result"] == before["result"]

    def test_the_second_yes_accepts_and_the_series_goes_on(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)

        answer = yes(skat, table, 2)

        assert proposal_of(answer) == {"proposer_seat": 1, "agreed_seats": [1, 2]}
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
        assert table.record.series == Series(SERIES_LENGTH, 1, number=2)
        assert [chair["total"] for chair in table.read_as(table.watcher).json()["chairs"]] == [0, 0, 0]
        assert entries_of(skat, table) == []

    def test_a_viewer_sees_the_same_series_with_seats_only_during_a_proposal_and_after_the_end(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        during = [table.read_as(each).json()["series"] for each in (*headers_of(table), table.watcher)]
        assert all(view == during[0] for view in during)
        assert set(during[0]["end_proposal"]) == {"proposer_seat", "agreed_seats", "answer_by"}
        assert len(entries_of(skat, table)) == 2

        assert yes(skat, table, 3).status_code == 200

        after = [table.read_as(each).json()["series"] for each in (*headers_of(table), table.watcher)]
        assert all(view == after[0] for view in after)
        assert len(entries_of(skat, table)) == 2


class TestTheNo:
    @pytest.mark.parametrize("refuser", [1, 2, 3], ids=["the-proposer", "a-seat-that-agreed", "the-other"])
    def test_any_seated_no_clears_the_proposal_and_the_series_plays_on(self, skat, mid_series, refuser):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        answer = no(skat, table, refuser)

        assert (answer.status_code, proposal_of(answer), answer.json()["series"]["over"]) == (200, None, False)
        assert answer.json()["series"]["end_refused_seats"] == [refuser]

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
        assert standing_of(table) == (1, {1})

    def test_a_yes_after_a_no_is_refused_until_the_next_hand(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        no(skat, table, 2)

        answer = yes(skat, table, 3)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.END_REFUSED)
        assert table.record.series.end_proposal is None

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

    def test_the_next_hand_takes_the_refusal_away_and_allows_a_new_proposal(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        no(skat, table, 2)
        for seat in (1, 2, 3):
            tap_weiter(skat, headers_of(table)[seat - 1], table.table_id, f"weiter-{seat}", 2)
        assert deal_next(skat, table.table_id, accounts_of(table))
        assert table.read_as(table.watcher).json()["series"]["end_refused_seats"] == []

    def test_a_proposal_after_a_passed_in_hand_is_accepted_and_the_pauses_deal_clears_it(
        self, skat, after_a_passed_in_hand
    ):
        table = after_a_passed_in_hand
        yes(skat, table, 1)
        assert proposal_of(yes(skat, table, 2)) == {"proposer_seat": 1, "agreed_seats": [1, 2]}

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
        assert standing_of(table) == (1, {1})
        assert skat.sit(table.watcher, table.table_id, 2, command_id="sit-dora").status_code == 200

        assert proposal_of(yes(skat, table, 3)) == {"proposer_seat": 1, "agreed_seats": [1, 3]}
        ended = agree_to_end(skat, table.watcher, table.table_id, "yes-dora")

        assert ended.json()["series"]["over"] is True

    @pytest.mark.parametrize("leaver", [1, 2, 3])
    def test_an_away_hold_frees_no_chair_and_leaves_the_proposal_whole(self, skat, mid_series, leaver):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        skat.store.hold_due(table.table_id, accounts_of(table)[leaver - 1])
        freed = TableService(skat.store).free_held_chair(
            TableId(table.table_id), accounts_of(table)[leaver - 1], nullcontext(True)
        )

        assert freed is False
        assert standing_of(table) == (1, {1, 2})

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


class TestTheStreamOfAnEndedSeries:
    def opened_as(self, skat, table, headers):
        """The status of a table stream and its first message, which the stream is closed after."""
        skat.client.cookies.clear()
        with skat.client.stream("GET", f"{TABLES_PATH}/{table.table_id}{TABLE_EVENTS_SUFFIX}", headers=headers) as s:
            first = next(line for line in s.iter_lines() if line.startswith("data: "))
            return s.status_code, json.loads(first.removeprefix("data: "))

    def test_every_viewer_opens_the_live_table_with_its_finished_series_and_each_open_gives_its_slot_back(
        self, skat, mid_series
    ):
        table = mid_series
        end_early(skat, table)

        for headers in (*headers_of(table), table.watcher):
            for _ in range(DEFAULT_STREAMS_PER_ACCOUNT + 1):
                status, message = self.opened_as(skat, table, headers)

                assert status == 200
                assert (message["ended"], message["series"]["over"]) == (None, True)


class TestTheSilentMinute:
    def lapse(self, skat, table, seconds):
        later = datetime.now(UTC) + timedelta(seconds=seconds)
        return TableService(skat.store, now=lambda: later).lapse_end_answers(TableId(table.table_id))

    def test_a_proposal_left_unanswered_for_a_minute_ends_and_names_the_silent_seats(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)

        assert self.lapse(skat, table, END_ANSWER_SECONDS + 1).seconds_left is None

        series = table.read_as(table.watcher).json()["series"]
        assert (series["end_proposal"], series["end_refused_seats"], series["over"]) == (None, [3], False)

    def test_a_proposal_inside_its_minute_stands_and_says_how_long_it_has_left(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)

        left = self.lapse(skat, table, END_ANSWER_SECONDS - 10)

        assert 0 < left.seconds_left <= 10
        assert standing_of(table) == (1, {1})

    def test_a_table_that_is_gone_has_no_minute_left(self, skat):
        assert TableService(skat.store).lapse_end_answers(TableId("0" * 32)).seconds_left is None

    def test_a_yes_that_came_in_time_is_no_silence(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        yes(skat, table, 2)
        yes(skat, table, 3)

        assert self.lapse(skat, table, END_ANSWER_SECONDS + 1).seconds_left is None

        assert table.read_as(table.watcher).json()["series"]["over"] is True

    def test_a_restart_finds_each_standing_proposal_with_the_seconds_its_minute_has_left(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        later = datetime.now(UTC) + timedelta(seconds=20)

        left = TableService(skat.store, now=lambda: later).pending_end_answers()

        assert 0 < left[table.table_id] <= END_ANSWER_SECONDS - 19

    def test_a_restart_finds_a_proposal_whose_minute_ran_out_while_no_server_ran_with_none_left(self, skat, mid_series):
        table = mid_series
        yes(skat, table, 1)
        later = datetime.now(UTC) + timedelta(seconds=END_ANSWER_SECONDS * 5)

        left = TableService(skat.store, now=lambda: later).pending_end_answers()

        assert left[table.table_id] == 0.0


class TestTheMinuteTheRouteStarts:
    """The presence the app wires runs the minute a yes starts, here on the test's clock with no scan of the store."""

    @pytest.fixture
    def skat(self, sign_in_settings, time):
        skat = Skat(
            sign_in_settings,
            now=time.moment,
            chair_clock=time.clock,
            chair_scheduler=time,
            rounds=ServerRounds(end_answer_recovery_seconds=END_ANSWER_SECONDS * 100),
        )
        with skat.client:
            yield skat

    def test_a_yes_posted_to_the_route_ends_the_proposal_a_minute_later_and_names_the_silent_seats(
        self, skat, time, mid_series
    ):
        yes(skat, mid_series, 1)
        yes(skat, mid_series, 2)

        skat.client.portal.call(time.advance, END_ANSWER_SECONDS - 1)
        assert series_of(mid_series)["end_proposal"] is not None
        skat.client.portal.call(time.advance, 1)

        series = series_of(mid_series)
        assert (series["end_proposal"], series["end_refused_seats"], series["over"]) == (None, [3], False)


class TestTheMinuteOfNewSeries:
    """At the series' end the first „Neue Serie“ starts a minute, after which a seated seat that stayed silent ends the
    table.
    """

    @pytest.fixture
    def skat(self, sign_in_settings, time):
        skat = Skat(
            sign_in_settings,
            now=time.moment,
            chair_clock=time.clock,
            chair_scheduler=time,
            rounds=ServerRounds(end_answer_recovery_seconds=END_ANSWER_SECONDS * 100),
        )
        with skat.client:
            yield skat

    @pytest.fixture
    def ended(self, skat):
        table, _ = play_a_series(skat, 3)
        return table

    def tap(self, skat, table, seat):
        return tap_new_series(skat, headers_of(table)[seat - 1], table.table_id, f"tap-new-{seat}")

    def test_the_first_tap_shows_the_minute_to_every_page_and_the_chairs_that_chose(self, skat, ended):
        answer = self.tap(skat, ended, 1)

        series = table_series = answer.json()["series"]
        assert series["new_series_answer_by"] is not None
        assert [chair["ready"] for chair in answer.json()["chairs"]] == [True, False, False]
        assert ended.read_as(ended.watcher).json()["series"] == table_series

    def test_a_seat_silent_for_the_minute_ends_the_table_as_a_close_that_names_nobody(self, skat, time, ended):
        self.tap(skat, ended, 1)
        self.tap(skat, ended, 2)

        skat.client.portal.call(time.advance, END_ANSWER_SECONDS - 1)
        assert isinstance(skat.store.tables[ended.table_id], TableRecord)
        skat.client.portal.call(time.advance, 1)

        answer = ended.read_as(ended.watcher).json()
        assert (answer["ended"]["reason"], answer["ended"]["closed_by_name"], answer["ended"]["game_count"]) == (
            EndReason.CLOSED,
            None,
            3,
        )

    def test_every_seat_that_chose_in_time_deals_the_next_series_and_no_minute_ends_it(self, skat, time, ended):
        for seat in (1, 2, 3):
            assert self.tap(skat, ended, seat).status_code == 200
        assert deal_next(skat, ended.table_id, [chair.occupant.account_id for chair in ended.record.chairs])

        skat.client.portal.call(time.advance, END_ANSWER_SECONDS + 1)

        table = skat.store.tables[ended.table_id]
        assert isinstance(table, TableRecord)
        assert table.series.number == 2

    def test_a_tap_after_the_minute_is_refused_and_the_table_ends(self, skat, time, ended):
        self.tap(skat, ended, 1)
        skat.client.portal.call(time.advance, END_ANSWER_SECONDS - 1)

        late = TableService(skat.store, now=lambda: time.moment() + timedelta(seconds=2))

        answered = late.start_new_series(
            Actor(account_id=ended.record.chairs[1].occupant.account_id, display_name="Ben"),
            NewSeriesCommand("tap-late", ended.table_id, 1),
            frozenset(),
        )
        assert answered.refusal is Refusal.ANSWER_TIME_OVER

    def test_the_lapse_of_another_pod_ends_the_table_in_its_own_transaction(self, skat, time, ended):
        self.tap(skat, ended, 1)
        another_pod = TableService(skat.store, now=lambda: time.moment() + timedelta(seconds=END_ANSWER_SECONDS))

        first = another_pod.lapse_end_answers(TableId(ended.table_id))

        assert first.table_stopped
        assert not isinstance(skat.store.tables[ended.table_id], TableRecord)


class TestTheMinuteOfAProposalFoundInTheStore:
    @pytest.fixture
    def skat(self, sign_in_settings, time):
        skat = Skat(sign_in_settings, now=time.moment, chair_clock=time.clock, chair_scheduler=time)
        with skat.client:
            yield skat

    def test_a_proposal_whose_timer_ran_on_a_pod_that_is_gone_ends_while_the_server_runs(self, skat, time, mid_series):
        first = mid_series.record.chairs[0].occupant
        another_pod = TableService(skat.store, now=time.moment)
        answered = another_pod.agree_to_end_series(
            Actor(account_id=first.account_id, display_name=first.display_name),
            SeriesEndCommand("command-yes-elsewhere", mid_series.table_id),
            frozenset(accounts_of(mid_series)),
        )
        assert answered.refusal is None

        skat.client.portal.call(time.advance, END_ANSWER_SECONDS + END_ANSWER_RECOVERY_SECONDS)

        series = series_of(mid_series)
        assert (series["end_proposal"], series["end_refused_seats"]) == (None, [2, 3])


def test_a_restart_ends_the_stored_proposal_when_the_minute_it_has_left_is_over(sign_in_settings):
    before_time, after_time = FakeTime(), FakeTime()
    unscanned = END_ANSWER_SECONDS * 100
    before = Skat(
        sign_in_settings,
        now=before_time.moment,
        chair_clock=before_time.clock,
        chair_scheduler=before_time,
        rounds=ServerRounds(end_answer_recovery_seconds=unscanned),
    )
    with before.client:
        table, _ = play_a_series(before, SERIES_LENGTH, games_to_play=2)
        yes(before, table, 1)
    after_time.now = before_time.now + END_ANSWER_SECONDS - 10
    after = Skat(
        sign_in_settings,
        store=before.store,
        stores=before.stores,
        now=after_time.moment,
        chair_clock=after_time.clock,
        chair_scheduler=after_time,
        rounds=ServerRounds(end_answer_recovery_seconds=unscanned),
    )

    with after.client:
        after.client.portal.call(after_time.advance, 9)
        assert after.store.tables[table.table_id].series.end_proposal is not None
        after.client.portal.call(after_time.advance, 1)

    series = after.store.tables[table.table_id].series
    assert (series.end_proposal, series.end_refused_by) == (None, frozenset({2, 3}))
