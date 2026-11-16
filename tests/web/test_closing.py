import pytest

from skat.table.records import EndReason, TableRecord
from skat.web.closing import TABLE_CLOSE_SUFFIX
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.series import headers_of, play_a_series
from tests.web.support.skat import FETCH, UNKNOWN_ID, streams_of

CLOSE_COMMAND_ID = "command-close"


def close(skat, headers, table_id, command_id=CLOSE_COMMAND_ID):
    answer = skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_CLOSE_SUFFIX}",
        json={"command_id": command_id},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )
    skat.client.cookies.clear()
    return answer


@pytest.fixture
def table(skat):
    headers, owner = skat.member()
    skat.client.cookies.clear()
    return headers, owner, skat.create(headers).json()["id"]


class TestClose:
    def test_the_opener_ends_the_table_and_the_answer_names_the_closer(self, skat, table):
        headers, owner, table_id = table

        answer = close(skat, headers, table_id)

        assert answer.status_code == 200, answer.text
        assert answer.headers["cache-control"] == "no-store"
        assert answer.json()["ended"] == {
            "reason": EndReason.CLOSED.value,
            "empty_seconds": None,
            "unplayed_days": None,
            "closed_by_name": owner.username,
            "standings": None,
            "game_count": None,
        }
        assert not isinstance(skat.store.tables[table_id], TableRecord)

    def test_every_open_stream_shows_the_end_with_the_closers_name_and_stops(self, skat, table):
        headers, owner, table_id = table
        watcher, _ = skat.member()
        with streams_of(skat, table_id, [(headers, owner), (watcher, None)]) as streams:
            close(skat, headers, table_id)

            ended = [next(messages) for messages in streams]

        assert [view["ended"]["closed_by_name"] for view in ended] == [owner.username, owner.username]

    def test_the_old_link_shows_who_closed_the_table_to_everyone(self, skat, table):
        headers, owner, table_id = table
        visitor, _ = skat.member()
        close(skat, headers, table_id)

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=visitor)

        assert answer.json()["ended"]["closed_by_name"] == owner.username

    def test_a_retry_answers_the_first_outcome(self, skat, table):
        headers, _, table_id = table
        first = close(skat, headers, table_id).json()

        assert close(skat, headers, table_id).json() == first

    def test_a_command_id_that_a_create_used_is_refused(self, skat, table):
        headers, _, table_id = table

        assert close(skat, headers, table_id, command_id="command-0001").status_code == 409

    def test_a_person_who_did_not_open_the_table_is_refused_and_nothing_changes(self, skat, table):
        _, _, table_id = table
        visitor, _ = skat.member()
        skat.sit(visitor, table_id, 2)
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        answer = close(skat, visitor, table_id)

        assert (answer.status_code, answer.json()) == (409, {"reason": "not-allowed", "holder_name": None})
        assert before == (skat.store.tables, skat.store.receipts)

    def test_the_view_of_a_live_table_marks_it_only_for_its_opener(self, skat, table):
        headers, _, table_id = table
        visitor, _ = skat.member()

        opener_view = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()
        visitor_view = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=visitor).json()

        assert (opener_view["opened_by_me"], visitor_view["opened_by_me"]) == (True, False)

    def test_an_unknown_table_is_not_found(self, skat):
        headers, _ = skat.member()

        assert close(skat, headers, UNKNOWN_ID).status_code == 404

    def test_signed_out_writes_nothing(self, skat, table):
        _, _, table_id = table
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        assert close(skat, FETCH, table_id).status_code == 401
        assert before == (skat.store.tables, skat.store.receipts)


class TestClosingATableThatFinishedGames:
    @pytest.fixture
    def closed(self, skat):
        """A played series of three games whose opener closed it."""
        table, _ = play_a_series(skat)
        opener = headers_of(table)[0]
        assert close(skat, opener, table.table_id).status_code == 200
        return table

    def test_the_old_link_answers_the_games_played_and_the_standings_and_names_nobody(self, skat, closed):
        answer = skat.client.get(f"{TABLES_PATH}/{closed.table_id}", headers=closed.watcher)

        ended = answer.json()["ended"]
        assert (ended["reason"], ended["closed_by_name"], ended["game_count"]) == ("closed", None, 3)
        assert sorted(standing["seat"] for standing in ended["standings"]) == [1, 2, 3]
        assert {standing["kind"] for standing in ended["standings"]} == {"person"}
        assert ended["standings"][0]["place"] == 1

    def test_the_list_and_a_game_of_the_closed_table_are_those_of_its_last_series(self, skat, closed):
        listed = skat.client.get(f"{TABLES_PATH}/{closed.table_id}{TABLE_LIST_SUFFIX}", headers=closed.watcher)
        sheet = skat.client.get(f"{TABLES_PATH}/{closed.table_id}{TABLE_LIST_SUFFIX}/2", headers=closed.watcher)

        assert [entry["number"] for entry in listed.json()["entries"]] == [1, 2, 3]
        assert (sheet.status_code, sheet.json()["number"]) == (200, 2)
