from dataclasses import replace

import pytest
from structlog.testing import capture_logs

from skat.engine.bidding import Pass
from skat.engine.deal import Position, next_dealer
from skat.table.records import HandProgress, Refusal
from skat.web.paused import PAUSED_TABLES_PATH
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    NAMED_FAILURE,
    OvertakenStore,
    end_the_first_game,
    occupied_seats,
    view_of_version,
)
from tests.web.support.skat import FakeTime, Skat, streams_of

FIRST_RESULT = 1


WEITER_COMMAND_ID = "weiter-0001"


def weiter(server, headers, table_id, *, command_id=WEITER_COMMAND_ID, ordinal=FIRST_RESULT, **extra):
    answer = server.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": command_id, "ordinal": ordinal, **extra},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )
    server.client.cookies.clear()
    return answer


def marks(view):
    return [chair["ready"] for chair in view["chairs"]]


def stored_marks(server, table_id):
    return [chair.ready for chair in server.store.tables[table_id].chairs]


def advance(server, time, seconds):
    server.client.portal.call(time.advance, seconds)


@pytest.fixture
def table(server):
    """Anna, Ben and Cleo in seats 1 to 3, the fourth member Dora watching; returns the id and all four."""
    table_id, people = seated_three(server)
    server.client.cookies.clear()
    return table_id, people


class TestWeiter:
    def test_the_first_tap_marks_the_chair_for_every_viewer_bumps_the_version_once_and_deals_nothing(
        self, server, table
    ):
        table_id, people = table
        before = end_the_first_game(server.store, table_id)
        with streams_of(server, table_id, people) as streams:
            answer = weiter(server, people[0][0], table_id)

            assert answer.status_code == 200, answer.text
            assert answer.headers["cache-control"] == "no-store"
            assert marks(answer.json()) == [True, False, False]
            for messages in streams:
                view = view_of_version(messages, before.version + 1)
                assert (marks(view), view["hand"], view["result"]["ordinal"]) == (
                    [True, False, False],
                    None,
                    FIRST_RESULT,
                )
        after = server.store.tables[table_id]
        assert (after.version, after.hand) == (before.version + 1, None)

    def test_the_third_tap_with_all_connected_deals_at_once_and_clears_every_mark(self, server, table):
        table_id, people = table
        before = end_the_first_game(server.store, table_id, 1, 2)
        with streams_of(server, table_id, people) as streams:
            answer = weiter(server, people[2][0], table_id)

            assert answer.status_code == 200, answer.text
            after = server.store.tables[table_id]
            assert after.version == before.version + 2
            assert (after.dealer, stored_marks(server, table_id)) == (next_dealer(DEALER_SEAT), [False] * 3)
            for messages in streams:
                view = view_of_version(messages, after.version)
                assert (marks(view), view["result"]) == ([False] * 3, None)
                assert view["hand"] is not None

    def test_a_tap_after_the_deal_deals_nothing_more(self, server, table):
        table_id, people = table
        end_the_first_game(server.store, table_id, 1, 2)
        with streams_of(server, table_id, people[:3]):
            weiter(server, people[2][0], table_id)
            dealt = server.store.tables[table_id]

            late = weiter(server, people[1][0], table_id, command_id="weiter-late")

        assert (late.status_code, late.json()["reason"]) == (409, Refusal.NO_RESULT)
        assert server.store.tables[table_id] == dealt

    def test_a_second_tap_from_a_ready_chair_is_accepted_and_changes_nothing(self, server, table):
        table_id, people = table
        end_the_first_game(server.store, table_id)
        weiter(server, people[0][0], table_id)
        marked = server.store.tables[table_id]

        again = weiter(server, people[0][0], table_id, command_id="weiter-other-tab")

        assert again.status_code == 200, again.text
        assert marks(again.json()) == [True, False, False]
        assert server.store.tables[table_id] == marked

    @pytest.mark.parametrize(
        ("state", "seat", "ordinal", "reason"),
        [
            pytest.param("result", 1, FIRST_RESULT + 1, Refusal.STALE_RESULT, id="another-result"),
            pytest.param("hand", 1, FIRST_RESULT, Refusal.NO_RESULT, id="a-hand-runs"),
            pytest.param("passed-in", 1, FIRST_RESULT, Refusal.NO_RESULT, id="a-passed-in-hand"),
            pytest.param("result", 4, FIRST_RESULT, Refusal.NOT_SEATED, id="a-watcher"),
        ],
    )
    def test_a_refused_tap_names_its_reason_and_changes_nothing(self, server, table, state, seat, ordinal, reason):
        table_id, people = table
        if state == "result":
            end_the_first_game(server.store, table_id)
        elif state == "passed-in":
            steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
            record = server.store.tables[table_id]
            server.store.tables[table_id] = replace(record, hand=None, progress=HandProgress(steps))
        before = server.store.tables[table_id]

        answer = weiter(server, people[seat - 1][0], table_id, ordinal=ordinal)

        assert (answer.status_code, answer.json()["reason"]) == (409, reason)
        assert server.store.tables[table_id] == before

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"ordinal": "1"}, id="ordinal-as-text"),
            pytest.param({"ordinal": FIRST_RESULT - 1}, id="ordinal-below-the-first"),
            pytest.param({"seat": 1}, id="names-a-chair"),
        ],
    )
    def test_refuses_a_malformed_request_and_writes_nothing(self, server, table, body):
        table_id, people = table
        before = end_the_first_game(server.store, table_id)

        answer = weiter(server, people[0][0], table_id, **body)

        assert answer.status_code == 422
        assert server.store.tables[table_id] == before

    def test_an_unknown_table_is_not_found(self, server, table):
        _, people = table

        assert weiter(server, people[0][0], "0" * 32).status_code == 404

    def test_standing_up_takes_back_only_the_own_mark(self, server, table):
        table_id, people = table
        end_the_first_game(server.store, table_id, 1, 2, 3)

        answer = server.stand(people[0][0], table_id)
        server.client.cookies.clear()

        assert answer.status_code == 200, answer.text
        assert (occupied_seats(server, table_id), stored_marks(server, table_id)) == ({2, 3}, [False, True, True])


class TestRetry:
    def test_a_deal_lost_after_the_commit_follows_the_retry_and_a_further_retry_deals_nothing(self, hold, time):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)

        def store_goes_down():
            raise ConnectionError(FAILURE_NAMING_AN_ACCOUNT)

        with server.client:
            table_id, people = seated_three(server)
            server.client.cookies.clear()
            before = end_the_first_game(server.store, table_id, 1, 2)
            with streams_of(server, table_id, people[:3]):
                store.after_commit_of_command = (
                    WEITER_COMMAND_ID,
                    lambda: setattr(store, "meanwhile", store_goes_down),
                )
                with capture_logs() as logs:
                    first = weiter(server, people[2][0], table_id)
                assert first.status_code == 200, first.text
                assert store.tables[table_id].hand is None
                assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]

                retried = weiter(server, people[2][0], table_id)
                dealt = store.tables[table_id]
                again = weiter(server, people[2][0], table_id)

        assert (retried.status_code, again.status_code) == (200, 200)
        assert (dealt.version, dealt.hand is not None) == (before.version + 2, True)
        assert store.tables[table_id] == dealt


class TestAway:
    def test_an_away_member_delays_the_deal_until_their_stream_opens(self, server, table):
        table_id, people = table
        before = end_the_first_game(server.store, table_id, 1, 3)
        with streams_of(server, table_id, [people[0], people[2]]):
            weiter(server, people[1][0], table_id)
            assert server.store.tables[table_id].hand is None

            with streams_of(server, table_id, people[1:2]):
                after = server.store.tables[table_id]

        assert (after.version, after.hand is not None) == (before.version + 2, True)

    def test_an_away_member_s_hold_frees_nothing_between_games_and_deals_nothing(self, server, hold, time, table):
        table_id, people = table
        end_the_first_game(server.store, table_id, 1, 2, 3)
        with streams_of(server, table_id, people[:1]):
            pass
        with streams_of(server, table_id, people[1:3]):
            advance(server, time, hold.settings.chair_hold_seconds + 1)

            assert occupied_seats(server, table_id) == {1, 2, 3}
            assert stored_marks(server, table_id) == [True, True, True]
            assert server.store.tables[table_id].hand is None


class TestSitDuringAResult:
    @pytest.mark.parametrize(
        ("ready_before", "deals"),
        [pytest.param((1, 2), True, id="the-others-ready"), pytest.param((1,), False, id="one-other-not-ready")],
    )
    def test_the_sitter_counts_as_ready_and_the_deal_follows_once_all_are(self, server, table, ready_before, deals):
        table_id, people = table
        end_the_first_game(server.store, table_id, *ready_before)
        server.stand(people[2][0], table_id)
        server.client.cookies.clear()
        stood = server.store.tables[table_id]
        with streams_of(server, table_id, [people[0], people[1], people[3]]):
            answer = server.sit(people[3][0], table_id, 3, command_id="command-sit-dora")
            server.client.cookies.clear()

        after = server.store.tables[table_id]
        assert answer.status_code == 200, answer.text
        assert answer.json()["hand"] is None
        assert answer.json()["chairs"][2]["ready"] is True
        assert (after.hand is not None, after.version) == (deals, stood.version + 1 + deals)


def test_a_restart_with_three_marks_deals_once_when_the_streams_reopen(sign_in_settings):
    settings = sign_in_settings()
    time = FakeTime()
    before_restart = Skat(lambda: settings, chair_clock=time.clock, chair_scheduler=time)
    with before_restart.client:
        table_id, people = seated_three(before_restart)
        before = end_the_first_game(before_restart.store, table_id, 1, 2, 3)

    after_restart = Skat(
        lambda: settings,
        store=before_restart.store,
        stores=before_restart.stores,
        chair_clock=time.clock,
        chair_scheduler=time,
    )
    with after_restart.client:
        with streams_of(after_restart, table_id, people[:3]):
            dealt = after_restart.store.tables[table_id]
        with streams_of(after_restart, table_id, people[:3]):
            pass

    assert (dealt.version, dealt.hand is not None) == (before.version + 1, True)
    assert after_restart.store.tables[table_id] == dealt


def test_a_restart_with_everyone_away_keeps_every_holders_listed_table_past_the_startup_holds_and_deals_at_weiter(hold):
    before_time = FakeTime()
    before_restart = Skat(lambda: hold, chair_clock=before_time.clock, chair_scheduler=before_time)
    with before_restart.client:
        table_id, people = seated_three(before_restart)
        before = end_the_first_game(before_restart.store, table_id)
    time = FakeTime()
    after_restart = Skat(
        lambda: hold,
        store=before_restart.store,
        stores=before_restart.stores,
        chair_clock=time.clock,
        chair_scheduler=time,
    )
    with after_restart.client:
        advance(after_restart, time, hold.settings.chair_hold_seconds + 1)
        kept = occupied_seats(after_restart, table_id)
        listed = {}
        for seat, (headers, _) in enumerate(people[:3], start=1):
            answer = after_restart.client.get(PAUSED_TABLES_PATH, headers=headers)
            after_restart.client.cookies.clear()
            listed[seat] = answer.json()["tables"]
        with streams_of(after_restart, table_id, people[:3]):
            for seat, (headers, _) in enumerate(people[:3], start=1):
                weiter(after_restart, headers, table_id, command_id=f"weiter-{seat}")
            dealt = after_restart.store.tables[table_id]

    assert kept == {1, 2, 3}
    for seat, tables in listed.items():
        (entry,) = tables
        assert entry["id"] == table_id
        assert [chair["is_mine"] for chair in entry["chairs"]] == [chair == seat for chair in (1, 2, 3)]
    assert (dealt.version, dealt.hand is not None) == (before.version + 3 + 1, True)
