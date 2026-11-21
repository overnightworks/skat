"""Two real `skat serve` processes on one database and one Redis serve one session: it is admitted by either, renewed
and ended for both, and it outlives the stop of one; they spend one sign-in budget, and a change at one reaches the
streams of the other."""

import json
import signal
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from webauth.policies import RateLimitPolicy

from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, SitDown
from skat.table.service import TableService
from skat.web.constants import AUTH_START_PATH, LOGOUT_PATH
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.support.pods import SAME_ORIGIN, new_command_id
from tests.support.redis import end_subscriptions, fresh_database_url
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

FORM_POST = {"content-type": "application/x-www-form-urlencoded", "origin": TEST_PUBLIC_ORIGIN}
BEHIND_THE_SEED = timedelta(hours=1)
SIGN_IN_BUDGET_REQUESTS = RateLimitPolicy().sign_in.max_requests
# Well under the stream's heartbeat, which also recovers a lost wake: a change that arrives in this time came by wake.
BEFORE_THE_HEARTBEAT_SECONDS = 5
CLEAN_EXIT = 0
SIGTERM_EXIT = -signal.SIGTERM


@pytest.fixture(autouse=True)
def an_emptied_redis(pods) -> Iterator[None]:
    """The limits that tests spend from the processes' Redis never reach another test."""
    fresh_database_url()
    yield
    fresh_database_url()


class TestASeededSession:
    def test_is_admitted_by_both_processes(self, pods):
        cookie, _ = pods.seeded_cookie()

        assert [pods.account_status(process, cookie) for process in (pods.first, pods.second)] == [200, 200]

    def test_renewed_by_the_first_process_is_admitted_by_the_second_with_the_renewed_expiry(self, pods):
        cookie, session_id = pods.seeded_cookie(expires_in=BEHIND_THE_SEED)
        seeded_expiry = pods.expiry_of(session_id)

        renewed_on_the_first = pods.account_status(pods.first, cookie)
        renewed_expiry = pods.expiry_of(session_id)

        assert (renewed_on_the_first, pods.account_status(pods.second, cookie)) == (200, 200)
        assert renewed_expiry > seeded_expiry
        assert pods.expiry_of(session_id) == renewed_expiry

    def test_ended_by_a_logout_on_the_first_process_is_refused_by_the_second(self, pods):
        cookie, session_id = pods.seeded_cookie()
        admitted_before = pods.account_status(pods.second, cookie)

        logout = pods.first.request("POST", LOGOUT_PATH, cookie=cookie, **FORM_POST)

        assert (admitted_before, logout.status_code) == (200, 200)
        assert (pods.account_status(pods.second, cookie), pods.expiry_of(session_id)) == (401, None)

    def test_is_admitted_again_by_the_first_process_after_it_was_stopped_with_sigterm_and_started_again(self, pods):
        cookie, _ = pods.seeded_cookie()

        exit_status = pods.first.stop()
        admitted_by_the_other_meanwhile = pods.account_status(pods.second, cookie)
        pods.first.start()

        assert exit_status in {CLEAN_EXIT, SIGTERM_EXIT}
        assert (admitted_by_the_other_meanwhile, pods.account_status(pods.first, cookie)) == (200, 200)


class TestAStopWithSigterm:
    def test_writes_the_process_stopped_line_before_the_process_ends(self, pods):
        logged_before = len(pods.second.log_lines("process.stopped"))

        exit_status = pods.second.stop()
        stopped_lines = len(pods.second.log_lines("process.stopped")) - logged_before
        pods.second.start()

        assert (exit_status, stopped_lines) == (SIGTERM_EXIT, 1)


class TestATableCommandLine:
    def test_of_an_opened_table_carries_the_id_the_request_answers_with(self, pods):
        cookie, _ = pods.member()

        table_id = pods.table_opened_by(pods.first, cookie)

        creations = [line for line in pods.first.log_lines("table_command.ended") if line["command"] == "create-table"]
        assert creations[-1]["table_id"] == table_id


class TestTheSignInBudget:
    def test_spent_through_the_first_process_is_refused_by_the_second(self, pods):
        spent = [pods.first.request("GET", AUTH_START_PATH).status_code for _ in range(SIGN_IN_BUDGET_REQUESTS)]

        assert set(spent) == {303}
        assert pods.second.request("GET", AUTH_START_PATH).status_code == 429


class TestAChangeAtOneProcess:
    def table_stream_of(self, pods, table_id: str, cookie: str):
        return pods.second.event_stream(
            f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", within_seconds=BEFORE_THE_HEARTBEAT_SECONDS, cookie=cookie
        )

    def test_a_seat_taken_through_the_first_process_reaches_a_table_stream_open_on_the_second_before_its_heartbeat(
        self, pods
    ):
        opener_cookie, _ = pods.member()
        guest_cookie, _ = pods.member()
        table_id = pods.table_opened_by(pods.first, opener_cookie)

        with self.table_stream_of(pods, table_id, opener_cookie) as events:
            before = json.loads(next(events))
            sat = pods.first.request(
                "POST",
                f"{TABLES_PATH}/{table_id}{TABLE_SIT_SUFFIX}",
                cookie=guest_cookie,
                json={"command_id": new_command_id(), "seat": 2},
                **SAME_ORIGIN,
            )
            after = json.loads(next(events))

        assert sat.status_code == 200
        assert after["version"] > before["version"]

    def test_a_row_changed_without_a_wake_reaches_a_table_stream_open_on_the_second_when_redis_ends_its_subscription(
        self, pods
    ):
        opener_cookie, _ = pods.member()
        _, guest_account = pods.member()
        table_id = pods.table_opened_by(pods.first, opener_cookie)
        tables = TableService(PostgresTableTransactions(pods.engine))

        with self.table_stream_of(pods, table_id, opener_cookie) as events:
            before = json.loads(next(events))
            tables.sit(Actor(guest_account, "Guest"), SitDown(new_command_id(), table_id, 2), frozenset())
            end_subscriptions(pods.redis_url)
            after = json.loads(next(events))

        assert after["version"] > before["version"]


class TestWhoWatchesAcrossPods:
    def watching(self, pods, process, table_id: str, cookie: str):
        return process.event_stream(
            f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", within_seconds=BEFORE_THE_HEARTBEAT_SECONDS, cookie=cookie
        )

    def test_a_watcher_on_the_first_process_is_counted_by_the_second(self, pods):
        opener_cookie, _ = pods.member()
        watcher_cookie, _ = pods.member()
        table_id = pods.table_opened_by(pods.first, opener_cookie)

        with self.watching(pods, pods.first, table_id, watcher_cookie) as events:
            next(events)
            counted = pods.watchers_at(pods.second, table_id, opener_cookie)

        assert counted == 1

    def test_one_account_with_a_stream_on_each_process_is_one_watcher_on_both(self, pods):
        opener_cookie, _ = pods.member()
        watcher_cookie, _ = pods.member()
        table_id = pods.table_opened_by(pods.first, opener_cookie)

        with (
            self.watching(pods, pods.first, table_id, watcher_cookie) as on_the_first,
            self.watching(pods, pods.second, table_id, watcher_cookie) as on_the_second,
        ):
            next(on_the_first)
            next(on_the_second)
            counted = [pods.watchers_at(process, table_id, opener_cookie) for process in (pods.first, pods.second)]

        assert counted == [1, 1]

    def test_a_watcher_arriving_and_leaving_on_the_first_process_reaches_a_stream_on_the_second_before_its_heartbeat(
        self, pods
    ):
        opener_cookie, _ = pods.member()
        watcher_cookie, _ = pods.member()
        table_id = pods.table_opened_by(pods.first, opener_cookie)

        with self.watching(pods, pods.second, table_id, opener_cookie) as observer:
            before = json.loads(next(observer))
            with self.watching(pods, pods.first, table_id, watcher_cookie) as events:
                next(events)
                arrived = json.loads(next(observer))
            left = json.loads(next(observer))

        assert [before["watchers"], arrived["watchers"], left["watchers"]] == [0, 1, 0]
