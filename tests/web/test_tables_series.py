import random
from contextlib import nullcontext
from dataclasses import replace

import pytest

from skat.table.records import Refusal, Series, TableId
from skat.table.service import TableService
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, with_known_deal
from tests.support.played_game import a_whole_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import Table
from tests.web.support.presence import end_the_first_game
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


def pass_the_hand_in(skat, table_id, people):
    """Everyone passes in turn until no hand runs."""
    while (view := read(skat, people[0][0], table_id).json())["hand"] is not None:
        seat = view["hand"]["auction"]["turn_seat"]
        answer = skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": f"pass-at-{view['version']}", "version": view["version"]},
            headers={"origin": TEST_PUBLIC_ORIGIN, **people[seat - 1][0]},
        )
        assert answer.status_code == 200, answer.text


def deal_next(skat, table_id, people):
    connected = frozenset(account.id for _, account in people)
    service = TableService(skat.store, random_source=random.Random(3))  # noqa: S311 - a seeded source makes the deal reproducible
    return service.deal_next(TableId(table_id), nullcontext(connected))


def play_through(skat, table_id, people, games):
    """Pass in `games` hands, dealing the next after each but the last."""
    for game in range(games):
        pass_the_hand_in(skat, table_id, people)
        if game < games - 1:
            assert deal_next(skat, table_id, people)


def tap_weiter(skat, headers, table_id, command_id, ordinal=1):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": command_id, "ordinal": ordinal},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def at_the_end_of_a_played_series(skat, table_id, length=3):
    """The first game played out and it was the last of a series of `length`."""
    record = end_the_first_game(skat.store, table_id)
    skat.store.tables[table_id] = replace(record, series=Series(length, length))


class TestOpening:
    def test_a_table_opened_with_a_length_answers_game_zero_of_that_length(self, skat):
        headers, _ = skat.member()

        answer = skat.create(headers, series_length=SERIES_LENGTH)

        assert answer.status_code == 200
        assert series_of(answer) == {"game_number": 0, "game_count": SERIES_LENGTH, "over": False}

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
        assert skat.create(headers).status_code == 409
        assert len(skat.store.tables) == 1

    def test_a_receipt_from_before_series_refuses_a_length(self, skat):
        headers, account = skat.member()
        skat.create(headers)
        key = (account.id, "command-0001")
        skat.store.receipts[key] = replace(skat.store.receipts[key], payload="{}")

        assert skat.create(headers, series_length=SERIES_LENGTH).status_code == 409


class TestCounting:
    def test_the_first_deal_is_game_one(self, skat):
        table_id, people = open_series(skat, 36)

        assert series_of(read(skat, people[0][0], table_id)) == {"game_number": 1, "game_count": 36, "over": False}

    def test_a_passed_in_hand_counts_and_leaves_no_list_row(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)

        pass_the_hand_in(skat, table_id, people)

        assert series_of(read(skat, people[0][0], table_id))["game_number"] == 1
        assert skat.store.tables[table_id].game_list == ()
        assert deal_next(skat, table_id, people)
        assert series_of(read(skat, people[0][0], table_id))["game_number"] == 2

    def test_twelve_passed_in_hands_end_the_series_and_nothing_deals_a_thirteenth(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)

        play_through(skat, table_id, people, SERIES_LENGTH)

        answer = read(skat, people[0][0], table_id).json()
        assert answer["series"] == {"game_number": 12, "game_count": 12, "over": True}
        assert answer["hand"] is None
        assert not deal_next(skat, table_id, people)
        assert series_of(read(skat, people[0][0], table_id))["game_number"] == SERIES_LENGTH

    def test_during_the_last_game_the_answer_says_twelve_of_twelve_and_not_over(self, skat):
        table_id, people = open_series(skat, SERIES_LENGTH)

        for _ in range(SERIES_LENGTH - 1):
            pass_the_hand_in(skat, table_id, people)
            assert deal_next(skat, table_id, people)

        answer = read(skat, people[0][0], table_id).json()
        assert answer["series"] == {"game_number": 12, "game_count": 12, "over": False}
        assert answer["hand"] is not None

    def test_a_passed_in_last_game_names_no_next_dealer(self, skat):
        table_id, people = open_series(skat, 3)

        play_through(skat, table_id, people, 3)

        answer = read(skat, people[0][0], table_id).json()
        assert (answer["series"]["over"], answer["passed_in"]) == (True, {"next_dealer_seat": None})

    def test_a_series_runs_on_while_a_person_leaves_and_another_sits_and_the_sit_that_deals_counts_once(self, skat):
        table_id, people = open_series(skat, 36)
        pass_the_hand_in(skat, table_id, people)
        stranger, _ = skat.member()
        skat.stand(people[1][0], table_id, command_id="stand-ben")

        skat.sit(stranger, table_id, 2, command_id="sit-dora")

        assert series_of(read(skat, people[0][0], table_id)) == {"game_number": 2, "game_count": 36, "over": False}


class TestTheEnd:
    def test_the_last_game_played_through_the_card_route_stands_as_a_result_and_ends_the_series(self, skat):
        table = Table(skat)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 3))
        table.declared_hand_game()

        table.played_out(each.card for each in a_whole_game(table.record))

        answer = table.read_as(table.watcher).json()
        assert answer["series"] == {"game_number": 3, "game_count": 3, "over": True}
        assert answer["result"]["ordinal"] == 1
        assert answer["hand"] is None

    def test_weiter_after_the_last_game_is_refused_each_time_and_changes_nothing(self, skat):
        table_id, people = open_series(skat, 3)
        at_the_end_of_a_played_series(skat, table_id)
        before = skat.store.tables[table_id]

        for number, (headers, _) in enumerate(people):
            answer = tap_weiter(skat, headers, table_id, f"weiter-{number}")
            assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.SERIES_OVER)

        assert skat.store.tables[table_id] == before

    def test_weiter_with_a_stale_ordinal_at_the_end_is_stale_before_it_is_series_over(self, skat):
        table_id, people = open_series(skat, 3)
        at_the_end_of_a_played_series(skat, table_id)

        answer = tap_weiter(skat, people[0][0], table_id, "weiter-stale", ordinal=2)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.STALE_RESULT)

    def test_a_sitter_at_the_end_is_not_marked_ready_and_nothing_deals(self, skat):
        table_id, people = open_series(skat, 3)
        at_the_end_of_a_played_series(skat, table_id)
        stranger, newcomer = skat.member()
        assert skat.stand(people[2][0], table_id, command_id="stand-cleo").status_code == 200

        assert skat.sit(stranger, table_id, 3, command_id="sit-dora").status_code == 200

        record = skat.store.tables[table_id]
        assert [chair.ready for chair in record.chairs] == [False, False, False]
        assert record.hand is None
        assert not deal_next(skat, table_id, [*people[:2], (stranger, newcomer)])

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
        assert set(answer.json()["series"]) == {"game_number", "game_count", "over"}
