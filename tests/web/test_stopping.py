import pytest

from skat.table.records import EndReason, TableRecord
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.stopping import TABLE_STOP_PLAYING_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.series import deal_next, headers_of, play_a_series, tap_new_series
from tests.web.support.skat import FETCH, UNKNOWN_ID, streams_of

STOP_COMMAND_ID = "command-stop"


def stop(skat, headers, table_id, command_id=STOP_COMMAND_ID):
    answer = skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_STOP_PLAYING_SUFFIX}",
        json={"command_id": command_id},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )
    skat.client.cookies.clear()
    return answer


@pytest.fixture
def ended(skat):
    """A series of three played to its end: the table waits for every seat's „Neue Serie“ or an „Aufhören“."""
    table, _ = play_a_series(skat)
    return table


class TestStopPlaying:
    def test_any_seated_person_ends_the_table_and_the_answer_names_nobody(self, skat, ended):
        answer = stop(skat, headers_of(ended)[1], ended.table_id)

        assert answer.status_code == 200, answer.text
        assert answer.headers["cache-control"] == "no-store"
        body = answer.json()["ended"]
        assert (body["reason"], body["closed_by_name"], body["game_count"]) == (EndReason.CLOSED.value, None, 3)
        assert sorted(standing["seat"] for standing in body["standings"]) == [1, 2, 3]
        assert not isinstance(skat.store.tables[ended.table_id], TableRecord)

    def test_every_open_stream_shows_the_end_and_stops(self, skat, ended):
        with streams_of(
            skat, ended.table_id, [(headers, None) for headers in (*headers_of(ended), ended.watcher)]
        ) as streams:
            stop(skat, headers_of(ended)[0], ended.table_id)

            seen = [next(messages) for messages in streams]

        assert [view["ended"]["reason"] for view in seen] == [EndReason.CLOSED.value] * 4

    def test_the_old_link_shows_the_standings_and_the_games_and_names_nobody_to_everyone(self, skat, ended):
        stop(skat, headers_of(ended)[0], ended.table_id)

        answer = skat.client.get(f"{TABLES_PATH}/{ended.table_id}", headers=ended.watcher)
        listed = skat.client.get(f"{TABLES_PATH}/{ended.table_id}{TABLE_LIST_SUFFIX}", headers=ended.watcher)

        assert answer.json()["ended"]["closed_by_name"] is None
        assert answer.json()["ended"]["standings"][0]["place"] == 1
        assert [entry["number"] for entry in listed.json()["entries"]] == [1, 2, 3]

    def test_a_retry_answers_the_first_outcome(self, skat, ended):
        first = stop(skat, headers_of(ended)[0], ended.table_id).json()

        assert stop(skat, headers_of(ended)[0], ended.table_id).json() == first

    def test_a_command_id_that_a_create_used_is_refused(self, skat, ended):
        assert stop(skat, headers_of(ended)[0], ended.table_id, command_id="command-0001").status_code == 409

    def test_a_person_without_a_chair_is_refused_and_nothing_changes(self, skat, ended):
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        answer = stop(skat, ended.watcher, ended.table_id)

        assert (answer.status_code, answer.json()) == (409, {"reason": "not-seated", "holder_name": None})
        assert before == (skat.store.tables, skat.store.receipts)

    def test_a_series_that_is_not_over_is_refused_and_nothing_changes(self, skat):
        table, _ = play_a_series(skat, 12, games_to_play=2)
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        answer = stop(skat, headers_of(table)[0], table.table_id)

        assert (answer.status_code, answer.json()["reason"]) == (409, "series-not-over")
        assert before == (skat.store.tables, skat.store.receipts)

    def test_an_answer_after_the_end_finds_no_table(self, skat, ended):
        stop(skat, headers_of(ended)[0], ended.table_id)

        assert stop(skat, headers_of(ended)[1], ended.table_id, "command-stop-ben").status_code == 404
        assert tap_new_series(skat, headers_of(ended)[2], ended.table_id, "command-tap-late").status_code == 404

    def test_a_stop_after_the_next_series_was_dealt_is_refused_and_the_series_runs_on(self, skat, ended):
        for number, headers in enumerate(headers_of(ended), start=1):
            assert tap_new_series(skat, headers, ended.table_id, f"command-tap-{number}").status_code == 200
        assert deal_next(skat, ended.table_id, [chair.occupant.account_id for chair in ended.record.chairs])

        answer = stop(skat, headers_of(ended)[0], ended.table_id)

        assert (answer.status_code, answer.json()["reason"]) == (409, "series-not-over")
        assert isinstance(skat.store.tables[ended.table_id], TableRecord)

    def test_an_unknown_table_is_not_found(self, skat):
        headers, _ = skat.member()

        assert stop(skat, headers, UNKNOWN_ID).status_code == 404

    def test_signed_out_writes_nothing(self, skat, ended):
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        assert stop(skat, FETCH, ended.table_id).status_code == 401
        assert before == (skat.store.tables, skat.store.receipts)
