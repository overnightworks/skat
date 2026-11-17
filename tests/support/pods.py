"""Two real `skat serve` processes on one database and one Redis, and what a test does at them."""

import secrets
from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx2
from sqlalchemy.engine import make_url

from skat.store.migrate import create_store_engine
from skat.store.sign_in import PostgresSignInStores
from skat.web.constants import ACCOUNT_PATH
from skat.web.sign_in import LoggingAuditSink, build_sign_in_configs
from skat.web.tables import TABLE_SIT_SUFFIX, TABLES_PATH
from tests.support.in_memory_stores import in_process_rate_limits
from tests.support.postgres import created_database
from tests.support.redis import fresh_database_url
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN, build_sign_in_settings
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import SkatProcess

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import timedelta
    from pathlib import Path

FETCH = {"accept": "application/json"}
SAME_ORIGIN = {"origin": TEST_PUBLIC_ORIGIN}


def new_command_id() -> str:
    return secrets.token_hex(8)


def without_password(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql", password=None).render_as_string()


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

    def sit(self, process: SkatProcess, cookie: str, table_id: str, seat: int) -> None:
        sat = process.request(
            "POST",
            f"{TABLES_PATH}/{table_id}{TABLE_SIT_SUFFIX}",
            cookie=cookie,
            json={"command_id": new_command_id(), "seat": seat},
            **SAME_ORIGIN,
        )
        assert sat.status_code == httpx2.codes.OK, sat.text

    def table_at(self, process: SkatProcess, table_id: str, cookie: str) -> dict:
        """The table's view as the process answers it, read once."""
        return process.request("GET", f"{TABLES_PATH}/{table_id}", cookie=cookie, **FETCH).json()

    def restart_both(self) -> None:
        """Stop both processes with SIGTERM, as a rollout does, then start them again on the same settings."""
        for process in (self.first, self.second):
            process.stop()
        for process in (self.first, self.second):
            process.start()

    def watchers_at(self, process: SkatProcess, table_id: str, cookie: str) -> int:
        """How many accounts without a chair the process counts at the table, read once."""
        return process.request("GET", f"{TABLES_PATH}/{table_id}", cookie=cookie, **FETCH).json()["watchers"]

    def seeded_cookie(self, *, expires_in: timedelta | None = None) -> tuple[str, str]:
        """The cookie header of a session seeded through Skat's adapter, and the session's id."""
        member = seed_member(self.stores, self._config, expires_in=expires_in)
        return cookie_header(member.set_cookie_headers), member.session.id

    def expiry_of(self, session_id: str) -> object:
        session = self.stores.sessions.load(session_id)
        return None if session is None else session.expires_at


@contextmanager
def running_pods(postgres_template: str, directory: Path, **settings: str | int) -> Iterator[Pods]:
    """Two started processes on a database and a Redis database of their own, with `settings` beside the test's
    sign-in settings; the processes are killed at the end.
    """
    with created_database(postgres_template) as database_url:
        redis_url = fresh_database_url()
        sign_in = build_sign_in_settings(
            directory, database_url=without_password(database_url), redis_url=redis_url, **settings
        )
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
