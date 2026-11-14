"""Two real `skat serve` processes on one database serve one session: it is admitted by either, renewed and ended for
both, and it outlives the stop of one."""

import signal
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url

from skat.store.migrate import create_store_engine
from skat.store.sign_in import PostgresSignInStores
from skat.web.constants import ACCOUNT_PATH, LOGOUT_PATH
from skat.web.sign_in import LoggingAuditSink, build_sign_in_configs
from tests.support.postgres import created_database
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN, build_sign_in_settings
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import SkatProcess

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.postgres

FETCH = {"accept": "application/json"}
FORM_POST = {"content-type": "application/x-www-form-urlencoded", "origin": TEST_PUBLIC_ORIGIN}
BEHIND_THE_SEED = timedelta(hours=1)
CLEAN_EXIT = 0
SIGTERM_EXIT = -signal.SIGTERM


class Pods:
    """Two processes of Skat on one database, and the adapter that seeds the sessions they share."""

    def __init__(self, first: SkatProcess, second: SkatProcess, stores: PostgresSignInStores, engine, config) -> None:
        self.first = first
        self.second = second
        self.stores = stores
        self.engine = engine
        self._config = config

    def account_status(self, process: SkatProcess, cookie: str) -> int:
        return process.request("GET", ACCOUNT_PATH, cookie=cookie, **FETCH).status_code

    def seeded_cookie(self, *, expires_in: timedelta | None = None) -> tuple[str, str]:
        """The cookie header of a session seeded through Skat's adapter, and the session's id."""
        member = seed_member(self.stores, self._config, expires_in=expires_in)
        return cookie_header(member.set_cookie_headers), member.session.id

    def expiry_of(self, session_id: str) -> object:
        session = self.stores.sessions.load(session_id)
        return None if session is None else session.expires_at


def without_password(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql", password=None).render_as_string()


@pytest.fixture(scope="module")
def pods(postgres_template, tmp_path_factory) -> Iterator[Pods]:
    directory = tmp_path_factory.mktemp("pods")
    with created_database(postgres_template) as database_url:
        sign_in = build_sign_in_settings(directory, database_url=without_password(database_url))
        engine = create_store_engine(database_url)
        processes = [SkatProcess(sign_in.environment, directory / f"pod-{name}.log") for name in ("first", "second")]
        try:
            for process in processes:
                process.start()
            yield Pods(
                *processes,
                PostgresSignInStores(engine, audit=LoggingAuditSink()),
                engine,
                build_sign_in_configs(sign_in.settings).web_auth,
            )
        finally:
            for process in processes:
                process.kill()
            engine.dispose()


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
