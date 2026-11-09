from dataclasses import replace

import pytest

from skat.engine.deal import Position, positions_from
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT
from tests.web.support.series import play_a_series
from tests.web.support.skat import UNKNOWN_ID


def read_list(skat, headers, table_id):
    skat.client.cookies.clear()
    return skat.client.get(f"{TABLES_PATH}/{table_id}{TABLE_LIST_SUFFIX}", headers=headers)


def entries_of(answer):
    assert answer.status_code == 200, answer.text
    return answer.json()["entries"]


class TestReadingTheList:
    def test_a_seated_member_and_a_watcher_read_the_same_numbered_rows(self, skat):
        table, names = play_a_series(skat)
        seated = table.at[next(iter(table.at))]

        as_member = entries_of(read_list(skat, seated, table.table_id))
        as_watcher = entries_of(read_list(skat, table.watcher, table.table_id))

        assert as_member == as_watcher
        assert [row["number"] for row in as_member] == [1, 2, 3]
        assert {row["declarer_name"] for row in as_member} <= set(names)
        assert all(
            {"game", "hand", "ouvert", "announcement", "levels", "settled_value", "score"} <= set(row)
            for row in as_member
        )

    def test_a_table_without_a_finished_game_answers_an_empty_list(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        assert entries_of(read_list(skat, headers, table_id)) == []

    @pytest.mark.parametrize("table_id", [pytest.param(UNKNOWN_ID, id="unknown"), pytest.param("no-id", id="no-id")])
    def test_a_table_that_does_not_exist_is_not_found(self, skat, table_id):
        headers, _ = skat.member()

        assert read_list(skat, headers, table_id).status_code == 404

    def test_a_lost_game_scores_minus_twice_its_positive_value(self, skat):
        table, _ = play_a_series(skat)
        record = skat.store.tables[table.table_id]
        lost = replace(record.game_list[0], won=False, settled_value=36, score=-72)
        skat.store.tables[table.table_id] = replace(record, game_list=(lost, *record.game_list[1:]))

        row = entries_of(read_list(skat, table.watcher, table.table_id))[0]

        assert (row["settled_value"], row["score"]) == (36, -72)

    def test_a_declarer_who_stood_up_stays_named_and_a_nameless_row_names_nobody(self, skat):
        declarer_seat = next(seat for seat, each in positions_from(DEALER_SEAT).items() if each is Position.MIDDLEHAND)
        table, names = play_a_series(skat, swap_after_first=declarer_seat)
        record = table.record
        assert record.game_list[0].declarer_seat == declarer_seat

        named = entries_of(read_list(skat, table.watcher, table.table_id))
        nameless_list = tuple(replace(each, seat_names=(None, None, None)) for each in record.game_list)
        skat.store.tables[table.table_id] = replace(record, game_list=nameless_list)
        unnamed = entries_of(read_list(skat, table.watcher, table.table_id))

        assert named[0]["declarer_name"] == names[declarer_seat - 1]
        assert record.chairs[declarer_seat - 1].occupant.display_name != names[declarer_seat - 1]
        assert [row["declarer_name"] for row in unnamed] == [None, None, None]

    def test_the_answer_discloses_no_account_and_no_card(self, skat):
        table, _ = play_a_series(skat)
        accounts = {account for each in table.record.game_list for account in each.seat_accounts}

        answer = read_list(skat, table.watcher, table.table_id)

        assert all(account not in answer.text for account in accounts)
        assert "card" not in answer.text


def test_the_list_of_an_ended_table_is_empty(server, time, hold):
    headers, _ = server.member()
    table_id = server.create(headers).json()["id"]
    server.client.portal.call(time.advance, hold.settings.empty_table_seconds)

    assert entries_of(read_list(server, headers, table_id)) == []
