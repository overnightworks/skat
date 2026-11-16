"""Two real `skat serve` processes on one database and one Redis serve one session: it is admitted by either, renewed
and ended for both, and it outlives the stop of one; they spend one sign-in budget, and a change at one reaches the
streams of the other."""

import json
import secrets
import signal
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url
from webauth.policies import RateLimitPolicy

from skat.store.migrate import create_store_engine
from skat.store.sign_in import PostgresSignInStores
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, SitDown
from skat.table.service import TableService
from skat.web.constants import ACCOUNT_PATH, AUTH_START_PATH, LOGOUT_PATH
from skat.web.sign_in import LoggingAuditSink, build_sign_in_configs
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.support.in_memory_stores import in_process_rate_limits
from tests.support.postgres import created_database
from tests.support.redis import end_subscriptions, fresh_database_url
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN, build_sign_in_settings
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import SkatProcess

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

FETCH = {"accept": "application/json"}
SAME_ORIGIN = {"origin": TEST_PUBLIC_ORIGIN}
FORM_POST = {"content-type": "application/x-www-form-urlencoded", "origin": TEST_PUBLIC_ORIGIN}
BEHIND_THE_SEED = timedelta(hours=1)
SIGN_IN_BUDGET_REQUESTS = RateLimitPolicy().sign_in.max_requests
# Well under the stream's heartbeat, which also recovers a lost wake: a change that arrives in this time came by wake.
BEFORE_THE_HEARTBEAT_SECONDS = 5
CLEAN_EXIT = 0
SIGTERM_EXIT = -signal.SIGTERM


class Pods:
    """Two processes of Skat on one database, and the adapter that seeds the sessions they share."""

    def __init__(
        self, first: SkatProcess, second: SkatProcess, stores: PostgresSignInStores, engine, config, redis_url: str
    ) -> None:
        self.first = first
        self.second = second
        self.redis_url = redis_url
        self.stores = stores
        self.engine = engine
        self._config = config

    def account_status(self, process: SkatProcess, cookie: str) -> int:
        return process.request("GET", ACCOUNT_PATH, cookie=cookie, **FETCH).status_code

    def member(self) -> tuple[str, str]:
        """The cookie header of a new member, and the member's account id."""
        member = seed_member(self.stores, self._config)
        return cookie_header(member.set_cookie_headers), member.account.id

    def table_opened_by(self, process: SkatProcess, cookie: str) -> str:
        opened = process.request(
            "POST", TABLES_PATH, cookie=cookie, json={"command_id": new_command_id(), "series_length": 3}, **SAME_ORIGIN
        )
        return opened.json()["id"]

    def seeded_cookie(self, *, expires_in: timedelta | None = None) -> tuple[str, str]:
        """The cookie header of a session seeded through Skat's adapter, and the session's id."""
        member = seed_member(self.stores, self._config, expires_in=expires_in)
        return cookie_header(member.set_cookie_headers), member.session.id

    def expiry_of(self, session_id: str) -> object:
        session = self.stores.sessions.load(session_id)
        return None if session is None else session.expires_at


def new_command_id() -> str:
    return secrets.token_hex(8)


def without_password(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql", password=None).render_as_string()


@pytest.fixture(scope="module")
def pods(postgres_template, tmp_path_factory) -> Iterator[Pods]:
    directory = tmp_path_factory.mktemp("pods")
    with created_database(postgres_template) as database_url:
        redis_url = fresh_database_url()
        sign_in = build_sign_in_settings(directory, database_url=without_password(database_url), redis_url=redis_url)
        engine = create_store_engine(database_url)
        processes = [SkatProcess(sign_in.environment, directory / f"pod-{name}.log") for name in ("first", "second")]
        try:
            for process in processes:
                process.start()
            yield Pods(
                *processes,
                PostgresSignInStores(engine, audit=LoggingAuditSink()),
                engine,
                build_sign_in_configs(sign_in.settings, in_process_rate_limits()).web_auth,
                redis_url,
            )
        finally:
            for process in processes:
                process.kill()
            engine.dispose()


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
