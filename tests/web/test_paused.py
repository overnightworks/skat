from dataclasses import replace

import pytest

from skat.engine.deal import Position
from skat.web.mcp import READ_PAUSED_TABLES_TOOL
from skat.web.paused import PAUSED_TABLES_PATH
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, seated_three
from tests.web.support.playing import HERZ_GAME, Table
from tests.web.support.series import headers_of, pass_the_hand_in
from tests.web.support.skat import FETCH, NAVIGATION, AgentTable, Skat


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


ENTRY_KEYS = {"id", "chairs", "game_number", "game_count", "turn_seat", "result_waits"}
CHAIR_KEYS = {"seat", "occupant_name", "is_mine", "total"}


def read_paused(skat, headers):
    skat.client.cookies.clear()
    return skat.client.get(PAUSED_TABLES_PATH, headers=headers)


def paused_of(skat, headers):
    answer = read_paused(skat, headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["tables"]


def table_chairs(skat, headers, table_id):
    skat.client.cookies.clear()
    return skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()["chairs"]


class TestWhoReadsWhich:
    def test_each_holder_of_a_dealt_table_gets_it_with_only_his_own_chair_marked_and_a_watcher_gets_none(self, skat):
        table_id, people = seated_three(skat)

        for seat, (headers, _) in enumerate(people[:3], start=1):
            (entry,) = paused_of(skat, headers)
            assert entry["id"] == table_id
            assert [(chair["seat"], chair["occupant_name"]) for chair in entry["chairs"]] == [
                (chair["seat"], chair["occupant_name"]) for chair in table_chairs(skat, headers, table_id)
            ]
            assert [chair["is_mine"] for chair in entry["chairs"]] == [chair == seat for chair in (1, 2, 3)]
            assert (entry["game_number"], entry["game_count"]) == (1, 36)
            assert [chair["total"] for chair in entry["chairs"]] == [None, None, None]
            assert entry["result_waits"] is False
        assert paused_of(skat, people[3][0]) == []

    def test_a_table_where_no_hand_was_dealt_is_not_listed(self, skat):
        headers, _ = skat.member()
        skat.create(headers)

        assert paused_of(skat, headers) == []

    def test_follows_a_deal_a_stand_and_a_sit(self, skat):
        table = Table(skat)
        anna, ben, cleo = headers_of(table)
        pass_the_hand_in(skat, table.table_id, [anna, ben, cleo])

        assert len(paused_of(skat, ben)) == 1
        assert skat.stand(ben, table.table_id, command_id="ben-stands").status_code == 200
        assert paused_of(skat, ben) == []
        (entry,) = paused_of(skat, anna)
        assert entry["chairs"][1]["occupant_name"] is None
        assert skat.sit(table.watcher, table.table_id, 2, command_id="dora-sits").status_code == 200
        assert len(paused_of(skat, table.watcher)) == 1

    def test_a_table_without_a_series_has_no_game_number_and_no_series_length(self, skat):
        table_id, people = seated_three(skat)
        skat.store.tables[table_id] = replace(skat.store.tables[table_id], series=None)

        (entry,) = paused_of(skat, people[0][0])

        assert (entry["game_number"], entry["game_count"]) == (None, None)

    def test_a_pending_result_waits_for_nobody_and_each_chair_carries_the_total_the_table_shows(self, skat):
        table = Table(skat)
        table.declared_hand_game()
        table.played_out(HERZ_GAME)
        headers = headers_of(table)[0]

        (entry,) = paused_of(skat, headers)

        assert (entry["result_waits"], entry["turn_seat"]) == (True, None)
        assert [chair["total"] for chair in entry["chairs"]] == [
            chair["total"] for chair in table_chairs(skat, headers, table.table_id)
        ]

    def test_an_entry_names_the_seat_on_turn_and_no_card_no_count_and_no_account(self, skat):
        table = Table(skat)
        table.middlehand_bids()
        accounts = {each.occupant.account_id for each in table.record.chairs}

        (entry,) = paused_of(skat, headers_of(table)[0])

        assert entry["turn_seat"] == 3
        assert set(entry) == ENTRY_KEYS
        assert all(set(chair) == CHAIR_KEYS for chair in entry["chairs"])
        assert not cards_in(entry)
        assert accounts.isdisjoint(str(entry))


class TestTheGateAndTheHeaders:
    def test_a_fetch_without_a_session_gets_401_and_no_list(self, skat):
        answer = read_paused(skat, FETCH)

        assert answer.status_code == 401
        assert "tables" not in answer.text

    def test_a_navigation_without_a_session_is_sent_to_the_sign_in(self, skat):
        answer = read_paused(skat, NAVIGATION)

        assert answer.status_code == 302

    def test_the_answer_is_never_cached(self, skat):
        headers, _ = skat.member()

        assert read_paused(skat, headers).headers["cache-control"] == "no-store"


class TestTheTool:
    def test_an_agent_with_a_chair_reads_the_same_list_as_a_person_with_its_account(self, skat, agent):
        table = AgentTable(skat, agent, Position.FOREHAND)
        agent_headers = table.at[Position.FOREHAND]

        read = agent.call(READ_PAUSED_TABLES_TOOL)

        assert not read.is_error, read.text
        assert read.json() == {"tables": paused_of(skat, agent_headers)}
        assert [entry["id"] for entry in read.json()["tables"]] == [table.table_id]
