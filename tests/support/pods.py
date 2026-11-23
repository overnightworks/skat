"""Two real `skat serve` processes on one database and one Redis, and what a test does at them."""

import secrets
from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx2
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from skat.store.migrate import create_store_engine
from skat.store.schema import next_deals, tables
from skat.store.sign_in import PostgresSignInStores
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.constants import ACCOUNT_PATH
from skat.web.sign_in import LoggingAuditSink, build_sign_in_configs
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.support.in_memory_stores import in_process_rate_limits
from tests.support.postgres import created_database
from tests.support.redis import fresh_database_url
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN, build_sign_in_settings
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import SkatProcess

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
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

    def three_seated(self) -> tuple[str, list[str]]:
        """A table with three members seated, which deals the first hand: its id and their cookies by seat."""
        cookies = [self.member()[0] for _ in range(3)]
        table_id = self.table_opened_by(self.first, cookies[0])
        for seat in (2, 3):
            self.sit(self.first, cookies[seat - 1], table_id, seat)
        return table_id, cookies

    def pass_hand_in(self, process: SkatProcess, table_id: str, cookies: list[str]) -> None:
        """Every seat passes in its turn through the bid route, which ends the hand where nobody bids."""
        for _ in cookies:
            view = self.table_at(process, table_id, cookies[0])
            passed = process.request(
                "POST",
                f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
                cookie=cookies[view["hand"]["auction"]["turn_seat"] - 1],
                json={"command_id": new_command_id(), "version": view["version"]},
                **SAME_ORIGIN,
            )
            assert passed.status_code == httpx2.codes.OK, passed.text

    def events_path(self, table_id: str) -> str:
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def table_row(self, table_id: str):
        """The table's stored row: its version, wait and end."""
        with self.engine.connect() as connection:
            return connection.execute(
                select(
                    tables.c.version,
                    tables.c.empty_since,
                    tables.c.empty_seconds,
                    tables.c.ended_at,
                    tables.c.end_reason,
                ).where(tables.c.id == table_id)
            ).one()

    def next_deal_due_at(self, table_id: str):
        """When the table's stored pause is over, or None where it has none."""
        with self.engine.connect() as connection:
            return connection.execute(select(next_deals.c.due_at).where(next_deals.c.table_id == table_id)).scalar()

    @contextmanager
    def next_deals_held(self) -> Iterator[Callable[[], None]]:
        """No stored pause is dropped until the yielded release is called or the block ends, so none is dealt or lost
        and its due time stays as written.

        The database refuses every delete of a pause, which rolls back the sweeping pod's deal and keeps the row.
        """
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION hold_next_deals() RETURNS trigger LANGUAGE plpgsql AS "
                    "$$ BEGIN RAISE EXCEPTION 'the stored pauses are held'; END $$"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER hold_next_deals BEFORE DELETE ON next_deals "
                    "FOR EACH ROW EXECUTE FUNCTION hold_next_deals()"
                )
            )

        def release() -> None:
            with self.engine.begin() as connection:
                connection.execute(text("DROP TRIGGER IF EXISTS hold_next_deals ON next_deals"))
                connection.execute(text("DROP FUNCTION IF EXISTS hold_next_deals()"))

        try:
            yield release
        finally:
            release()

    def database_now(self):
        with self.engine.connect() as connection:
            return connection.execute(select(func.now())).scalar_one()

    def stop_both(self) -> None:
        """Stop both processes with SIGTERM, as a rollout does."""
        for process in (self.first, self.second):
            process.stop()

    def start_both(self) -> None:
        """Start both stopped processes again on the same settings."""
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
