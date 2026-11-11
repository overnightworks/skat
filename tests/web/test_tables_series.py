from dataclasses import replace

import pytest

from skat.table.records import Refusal, Series
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import Table
from tests.web.support.series import deal_next as deal_the_next
from tests.web.support.series import headers_of, pass_the_hand_in, play_a_series, tap_weiter
from tests.web.support.skat import FETCH

SERIES_LENGTH = 12


def series_of(answer):
    return answer.json()["series"]


def open_series(skat, length=36):
    """Anna opens, Ben and Cleo sit: the first game is dealt. Returns the table id and the three members."""
    people = [skat.member() for _ in range(3)]
    table_id = skat.create(people[0][0], series_length=length).json()["id"]
    for seat, (headers, _) in enumerate(people[1:], start=2):
        skat.sit(headers, table_id, seat, command_id=f"command-sit-{seat}")
    with_known_deal(skat, table_id)
    return table_id, people


def read(skat, headers, table_id):
    return skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)


def deal_next(skat, table_id, people):
    return deal_the_next(skat, table_id, [account.id for _, account in people])


def play_through(skat, table_id, people, games):
    """Pass in `games` hands, dealing the next after each but the last."""
    for game in range(games):
        pass_the_hand_in(skat, table_id, [headers for headers, _ in people])
        if game < games - 1:
            assert deal_next(skat, table_id, people)


class TestOpening:
    def test_a_table_opened_with_a_length_answers_game_zero_of_that_length(self, skat):
        headers, _ = skat.member()

        answer = skat.create(headers, series_length=SERIES_LENGTH)

        assert answer.status_code == 200
        assert series_of(answer) == {
            "game_number": 0,
            "game_count": SERIES_LENGTH,
            "over": False,
            "standings": None,
            "end_proposal": None,
        }

    def test_a_table_opened_before_series_existed_reads_with_no_series_and_deals_on(self, skat):
        table_id, people = open_series(skat)
        skat.store.tables[table_id] = replace(skat.store.tables[table_id], series=None)

        assert series_of(read(skat, people[0][0], table_id)) is None
        play_through(skat, table_id, people, 2)
        assert series_of(read(skat, people[0][0], table_id)) is None

    def test_refuses_a_create_request_with_no_length_and_stores_nothing(self, skat):
        headers, _ = skat.member()

        answer = skat.client.post(
            TABLES_PATH, json={"command_id": "command-0001"}, headers={"origin": TEST_PUBLIC_ORIGIN, **headers}
        )

        assert answer.status_code == 422
        assert skat.store.tables == {}

    @pytest.mark.parametrize("length", [0, 2, 4, 100, 102, -3, "12", 12.0, True])
    def test_refuses_a_length_outside_the_range_or_not_an_integer_and_stores_nothing(self, skat, length):
        headers, _ = skat.member()

        assert skat.create(headers, series_length=length).status_code == 422
        assert skat.store.tables == {}

    @pytest.mark.parametrize("length", [3, 36, 99])
    def test_takes_each_multiple_of_three_up_to_the_largest(self, skat, length):
        headers, _ = skat.member()

        assert series_of(skat.create(headers, series_length=length))["game_count"] == length

    def test_refuses_a_length_on_a_sit_a_stand_and_a_command(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)
        stranger, _ = skat.member()

        assert skat.sit(stranger, table_id, 1, series_length=SERIES_LENGTH).status_code == 422
        assert skat.stand(people[0][0], table_id, series_length=SERIES_LENGTH).status_code == 422
        refused = skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_READY_SUFFIX}",
            json={"command_id": "weiter-extra", "ordinal": 1, "series_length": SERIES_LENGTH},
            headers={"origin": TEST_PUBLIC_ORIGIN, **people[0][0]},
        )
        assert refused.status_code == 422


class TestRetry:
    def test_the_same_length_under_the_same_command_id_is_the_same_table(self, skat):
        headers, _ = skat.member()

        first = skat.create(headers, series_length=SERIES_LENGTH).json()

        assert skat.create(headers, series_length=SERIES_LENGTH).json() == first
        assert len(skat.store.tables) == 1

    def test_another_length_under_the_same_command_id_is_a_reused_id(self, skat):
        headers, _ = skat.member()
        skat.create(headers, series_length=SERIES_LENGTH)

        assert skat.create(headers, series_length=SERIES_LENGTH + 3).status_code == 409
        assert len(skat.store.tables) == 1

    def test_a_receipt_from_before_series_refuses_a_length(self, skat):
        headers, account = skat.member()
        skat.create(headers)
        key = (account.id, "command-0001")
        skat.store.receipts[key] = replace(skat.store.receipts[key], payload="{}")

        assert skat.create(headers, series_length=SERIES_LENGTH).status_code == 409


class TestOptions:
    def test_a_table_opened_with_the_switch_on_answers_it_on_from_its_creation(self, skat):
        headers, _ = skat.member()

        answer = skat.create(headers, options={"show_running_points": True})

        assert answer.json()["options"] == {
            "show_running_points": True,
            "kontra": None,
            "bock": None,
            "ramsch": None,
        }

    @pytest.mark.parametrize("extra", [{}, {"options": {}}, {"options": {"show_running_points": False}}])
    def test_a_table_opened_without_the_switch_or_with_it_off_answers_it_off(self, skat, extra):
        headers, _ = skat.member()

        assert skat.create(headers, **extra).json()["options"] == {
            "show_running_points": False,
            "kontra": None,
            "bock": None,
            "ramsch": None,
        }

    def test_a_read_and_a_watcher_see_the_options_the_table_was_opened_with(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers, options={"show_running_points": True}).json()["id"]
        watcher, _ = skat.member()

        assert read(skat, watcher, table_id).json()["options"] == {
            "show_running_points": True,
            "kontra": None,
            "bock": None,
            "ramsch": None,
        }

    @pytest.mark.parametrize(
        "options",
        [
            {"show_running_points": "yes"},
            {"show_running_points": 1},
            {"show_running_points": None},
            {"other": True},
            True,
        ],
    )
    def test_refuses_options_that_are_no_strict_switch_and_stores_nothing(self, skat, options):
        headers, _ = skat.member()

        assert skat.create(headers, options=options).status_code == 422
        assert skat.store.tables == {}

    @pytest.mark.parametrize(
        ("first", "retry"),
        [
            ({"options": {"show_running_points": True}}, {"options": {"show_running_points": True}}),
            ({}, {"options": {"show_running_points": False}}),
        ],
        ids=["same-switch-on", "switch-given-off-is-none"],
    )
    def test_a_retry_with_the_same_switch_is_the_same_table(self, skat, first, retry):
        headers, _ = skat.member()
        opened = skat.create(headers, **first).json()

        assert skat.create(headers, **retry).json() == opened
        assert len(skat.store.tables) == 1

    def test_another_switch_under_the_same_command_id_is_a_reused_id(self, skat):
        headers, _ = skat.member()
        skat.create(headers, options={"show_running_points": True})

        assert skat.create(headers).status_code == 409
        assert len(skat.store.tables) == 1

    def test_a_receipt_stored_before_options_replays_for_a_retry_without_them(self, skat):
        headers, account = skat.member()
        first = skat.create(headers).json()
        key = (account.id, "command-0001")
        skat.store.receipts[key] = replace(skat.store.receipts[key], payload='{"series_length":36}')

        assert skat.create(headers).json() == first

    def test_a_switch_on_changes_the_receipt_s_payload(self, skat):
        headers, account = skat.member()
        skat.create(headers, options={"show_running_points": True})

        assert skat.store.receipts[(account.id, "command-0001")].payload == (
            '{"series_length":36,"show_running_points":true}'
        )


class TestCounting:
    def test_the_first_deal_is_game_one(self, skat):
        table_id, people = open_series(skat, 36)

        assert series_of(read(skat, people[0][0], table_id)) == {
            "game_number": 1,
            "game_count": 36,
            "over": False,
            "standings": None,
            "end_proposal": None,
        }

    def test_a_passed_in_hand_counts_and_leaves_no_list_row(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)

        pass_the_hand_in(skat, table_id, [headers for headers, _ in people])

        assert series_of(read(skat, people[0][0], table_id))["game_number"] == 1
        assert skat.store.tables[table_id].game_list == ()
        assert deal_next(skat, table_id, people)
        assert series_of(read(skat, people[0][0], table_id))["game_number"] == 2

    def test_twelve_passed_in_hands_end_the_series_and_nothing_deals_a_thirteenth(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)

        play_through(skat, table_id, people, SERIES_LENGTH)

        answer = read(skat, people[0][0], table_id).json()
        assert answer["series"] == {
            "game_number": 12,
            "game_count": 12,
            "over": True,
            "standings": [],
            "end_proposal": None,
        }
        assert answer["hand"] is None
        assert not deal_next(skat, table_id, people)
        assert series_of(read(skat, people[0][0], table_id))["game_number"] == SERIES_LENGTH

    def test_during_the_last_game_the_answer_says_twelve_of_twelve_and_not_over(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)

        for _ in range(SERIES_LENGTH - 1):
            pass_the_hand_in(skat, table_id, [headers for headers, _ in people])
            assert deal_next(skat, table_id, people)

        answer = read(skat, people[0][0], table_id).json()
        assert answer["series"] == {
            "game_number": 12,
            "game_count": 12,
            "over": False,
            "standings": None,
            "end_proposal": None,
        }
        assert answer["hand"] is not None

    def test_a_passed_in_last_game_names_no_next_dealer(self, skat):
        table_id, people = open_series(skat, 3)

        play_through(skat, table_id, people, 3)

        answer = read(skat, people[0][0], table_id).json()
        assert (answer["series"]["over"], answer["passed_in"]) == (True, {"next_dealer_seat": None})

    def test_a_series_runs_on_while_a_person_leaves_and_another_sits_and_the_sit_that_deals_counts_once(self, skat):
        table_id, people = open_series(skat, 36)
        pass_the_hand_in(skat, table_id, [headers for headers, _ in people])
        stranger, _ = skat.member()
        skat.stand(people[1][0], table_id, command_id="stand-ben")

        skat.sit(stranger, table_id, 2, command_id="sit-dora")

        assert series_of(read(skat, people[0][0], table_id)) == {
            "game_number": 2,
            "game_count": 36,
            "over": False,
            "standings": None,
            "end_proposal": None,
        }


class TestTheEnd:
    def test_the_last_game_played_through_the_card_route_stands_as_a_result_and_ends_the_series(self, skat):
        table, _ = play_a_series(skat)

        answer = table.read_as(table.watcher).json()
        assert (answer["series"]["game_number"], answer["series"]["over"]) == (3, True)
        assert answer["result"]["ordinal"] == 3
        assert answer["hand"] is None

    def test_weiter_after_the_last_game_is_refused_each_time_and_changes_nothing(self, skat):
        table, _ = play_a_series(skat)
        before = table.record

        for number, headers in enumerate(headers_of(table)):
            answer = tap_weiter(skat, headers, table.table_id, f"weiter-end-{number}", ordinal=3)
            assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.SERIES_OVER)

        assert table.record == before

    def test_weiter_with_a_stale_ordinal_at_the_end_is_stale_before_it_is_series_over(self, skat):
        table, _ = play_a_series(skat)

        answer = tap_weiter(skat, headers_of(table)[0], table.table_id, "weiter-stale", ordinal=2)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.STALE_RESULT)

    def test_a_sitter_at_the_end_is_not_marked_ready_and_nothing_deals(self, skat):
        table, _ = play_a_series(skat)
        stranger, newcomer = skat.member()
        assert skat.stand(headers_of(table)[2], table.table_id, command_id="stand-cleo").status_code == 200

        assert skat.sit(stranger, table.table_id, 3, command_id="sit-dora").status_code == 200

        record = table.record
        assert [chair.ready for chair in record.chairs] == [False, False, False]
        assert record.hand is None
        accounts = frozenset(chair.occupant.account_id for chair in record.chairs)
        assert newcomer.id in accounts
        assert not deal_the_next(skat, table.table_id, accounts)

    def test_a_sitter_after_a_passed_in_last_game_is_not_marked_ready_and_nothing_deals(self, skat):
        table_id, people = open_series(skat, 3)
        play_through(skat, table_id, people, 3)
        stranger, _ = skat.member()
        assert skat.stand(people[2][0], table_id, command_id="stand-cleo").status_code == 200

        assert skat.sit(stranger, table_id, 3, command_id="sit-dora").status_code == 200

        record = skat.store.tables[table_id]
        assert [chair.ready for chair in record.chairs] == [False, False, False]
        assert record.hand is None
        assert record.series == Series(3, 3)

    def test_weiter_after_a_passed_in_last_game_is_refused_as_no_result(self, skat):
        table_id, people = open_series(skat, 3)
        play_through(skat, table_id, people, 3)

        answer = tap_weiter(skat, people[0][0], table_id, "weiter-after-pass")

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NO_RESULT)


class TestTheAnswer:
    def test_an_answer_with_a_series_reveals_no_card_to_a_watcher(self, skat):
        table_id, _ = open_series(skat, SERIES_LENGTH)
        watcher, _ = skat.member()

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers={**FETCH, **watcher})

        assert cards_in(answer.json()) == set()
        assert set(answer.json()["series"]) == {"game_number", "game_count", "over", "standings", "end_proposal"}


class TestTheStandings:
    def test_they_are_absent_while_the_series_runs(self, skat):
        table = Table(skat)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 1))

        assert series_of(table.read_as(table.watcher))["standings"] is None

    def test_a_played_series_ends_with_every_person_ranked_by_total_and_the_chairs_totals(self, skat):
        table, names = play_a_series(skat)

        answer = table.read_as(headers_of(table)[0]).json()

        standings = answer["series"]["standings"]
        assert {each["display_name"] for each in standings} == set(names)
        assert [each["total"] for each in standings] == sorted((each["total"] for each in standings), reverse=True)
        assert standings[0]["place"] == 1
        assert sorted(each["total"] for each in standings) == sorted(chair["total"] for chair in answer["chairs"])
        assert sum(each["won"] + each["lost"] for each in standings) == 3

    def test_a_watcher_sees_the_standings_a_player_sees_and_no_card(self, skat):
        table, _ = play_a_series(skat)

        as_player = table.read_as(headers_of(table)[0]).json()
        as_watcher = table.read_as(table.watcher).json()

        assert as_watcher["series"] == as_player["series"]
        assert as_watcher["series"]["standings"] is not None
        assert cards_in(as_watcher) == set()

    def test_a_person_who_stood_up_mid_series_keeps_a_row_under_their_name_beside_their_replacement(self, skat):
        table, names = play_a_series(skat, swap_after_first=2)

        answer = table.read_as(table.watcher).json()

        standings = {each["display_name"]: each for each in answer["series"]["standings"]}
        replacement = table.record.chairs[1].occupant.display_name
        assert set(standings) == {*names, replacement}
        assert standings[replacement]["total"] == answer["chairs"][1]["total"]
        assert (standings[names[1]]["won"], standings[names[1]]["lost"]) == (0, 0)

    def test_a_row_names_nobody_by_account_and_a_nameless_one_has_no_name(self, skat):
        table, _ = play_a_series(skat)
        record = skat.store.tables[table.table_id]
        accounts = {account for entry in record.game_list for account in entry.seat_accounts}
        nameless = tuple(replace(entry, seat_names=(None, None, None)) for entry in record.game_list)
        skat.store.tables[table.table_id] = replace(record, game_list=nameless)

        answer = table.read_as(table.watcher)

        standings = answer.json()["series"]["standings"]
        assert len(standings) == len(accounts)
        assert [each["display_name"] for each in standings] == [None] * len(accounts)
        assert all(account not in answer.text for account in accounts)
