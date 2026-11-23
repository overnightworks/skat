"""Skat's Postgres adapter of the sign-in ports: accounts, sessions and the serialised sign-in entry."""

import hashlib
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from webauth.ports import AccountEvent, AccountEventKind, AccountKind, StoreUnavailableError
from webauth.postgres import SessionStoreError
from webauth.store_contract import STORE_CHECKS, StoreAdapter

from skat.store.accounts import PostgresAccounts
from skat.store.migrate import SIGN_IN_LOCK_KEY, create_store_engine
from skat.store.schema import accounts, sessions
from skat.store.sessions import PostgresSessionRecords
from skat.store.sign_in import PostgresSignInStores
from skat.web.sign_in import LoggingAuditSink
from tests.support.postgres import row_count

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
LIFETIME = timedelta(days=30)
SUBJECT = "subject-anna"
POLL_SECONDS = 0.05
WAIT_DEADLINE_SECONDS = 10


class RecordingAudit:
    def __init__(self, failure=None):
        self.events = []
        self.failure = failure

    def account_event(self, event):
        if self.failure is not None:
            raise self.failure
        self.events.append(event)


@pytest.fixture
def audit():
    return RecordingAudit()


@pytest.fixture
def stores(engine, audit):
    return PostgresSignInStores(engine, audit=audit)


@dataclass(frozen=True)
class TransactionOnTheSameDatabase:
    """Builds a sign-in transaction in a process that shares nothing with the test, as the contract's second
    process needs it.
    """

    database_url: str

    def __call__(self):
        return PostgresSignInStores(create_store_engine(self.database_url), audit=LoggingAuditSink()).transaction


def created_event(subject=SUBJECT):
    return AccountEvent(kind=AccountEventKind.USER_CREATED, actor_id=None, subject_id=subject, role="user")


def new_session(entry, subject=SUBJECT, *, created_at=NOW, lifetime=LIFETIME, refresh_token="refresh-token"):
    return entry.sessions.create(
        subject,
        session_id=f"session-{uuid.uuid4().hex}",
        now=created_at,
        expires_at=created_at + lifetime,
        refresh_token=SecretStr(refresh_token),
        id_token=SecretStr("id-token"),
        account_language="de",
    )


def sign_in(stores, subject=SUBJECT, **session_options):
    """A first or further sign-in as the library enters it: the account is created when it is not there."""
    with stores.transaction() as entry:
        if entry.accounts.get(subject) is None:
            entry.accounts.create_for_subject(subject, "Anna", "user", AccountKind.PERSON)
            entry.audit.account_event(created_event(subject))
        return new_session(entry, subject, **session_options)


def an_entry_waits_for_the_lock(engine):
    with engine.connect() as connection:
        waiting = connection.execute(
            text(
                "SELECT count(*) FROM pg_locks"
                " WHERE locktype = 'advisory' AND NOT granted"
                " AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
                " AND (classid::bigint << 32) | objid::bigint = :key"
            ),
            {"key": SIGN_IN_LOCK_KEY},
        ).scalar_one()
    return waiting > 0


class TestTheStoreContract:
    @pytest.mark.parametrize("check", STORE_CHECKS, ids=lambda check: check.name)
    def test_keeps_the_duty_of_the_ports(self, check, engine, stores, database_url):
        with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as committing:
            adapter = StoreAdapter(
                accounts=PostgresAccounts(committing),
                sessions=stores.sessions,
                transaction=stores.transaction,
                transaction_in_another_process=TransactionOnTheSameDatabase(database_url),
            )

            check.run(adapter)


class TestASignInEntry:
    def test_that_raises_after_creating_an_account_and_a_session_stores_nothing_and_reports_no_event(
        self, engine, stores, audit
    ):
        def failing_sign_in():
            with stores.transaction() as entry:
                entry.accounts.create_for_subject(SUBJECT, "Anna", "user", AccountKind.PERSON)
                new_session(entry)
                entry.audit.account_event(created_event())
                raise RuntimeError("the entry fails")

        with pytest.raises(RuntimeError, match="the entry fails"):
            failing_sign_in()

        assert (row_count(engine, accounts), row_count(engine, sessions), audit.events) == (0, 0, [])

    def test_whose_audit_sink_raises_when_the_events_are_reported_is_rolled_back(self, engine, stores, audit):
        audit.failure = RuntimeError("the sink fails")

        with pytest.raises(RuntimeError, match="the sink fails"):
            sign_in(stores)

        assert (row_count(engine, accounts), row_count(engine, sessions)) == (0, 0)

    def test_whose_session_write_fails_keeps_the_tokens_out_of_the_error_text(self, stores):
        with pytest.raises(SessionStoreError) as failure:
            sign_in(stores, refresh_token="secret-refresh-token\x00")

        assert "secret-refresh-token" not in str(failure.value)

    def test_reports_its_events_in_order_when_it_ends_cleanly(self, stores, audit):
        sign_in(stores)

        assert audit.events == [created_event()]

    def test_of_a_subjects_first_sign_in_on_two_apps_at_once_stores_one_account_and_both_sessions(self, engine, audit):
        first_has_read = threading.Event()
        second_has_read = threading.Event()
        failures = []

        def first_sign_in(stores, has_read, creates_when):
            try:
                with stores.transaction() as entry:
                    known = entry.accounts.get(SUBJECT)
                    has_read.set()
                    creates_when()
                    if known is None:
                        entry.accounts.create_for_subject(SUBJECT, "Anna", "user", AccountKind.PERSON)
                    new_session(entry)
            except Exception as failure:
                failures.append(failure)

        def once_the_second_has_read_or_waits_for_the_lock():
            # Without the lock the second entry reads no account; with it the second entry waits outside.
            deadline = time.monotonic() + WAIT_DEADLINE_SECONDS
            while not second_has_read.wait(POLL_SECONDS) and not an_entry_waits_for_the_lock(engine):
                assert time.monotonic() < deadline

        first = threading.Thread(
            target=first_sign_in,
            args=(
                PostgresSignInStores(engine, audit=audit),
                first_has_read,
                once_the_second_has_read_or_waits_for_the_lock,
            ),
        )
        second = threading.Thread(
            target=first_sign_in,
            args=(PostgresSignInStores(engine, audit=audit), second_has_read, lambda: None),
        )
        first.start()
        assert first_has_read.wait(WAIT_DEADLINE_SECONDS)
        second.start()
        threads = [first, second]
        for thread in threads:
            thread.join(WAIT_DEADLINE_SECONDS)

        assert (failures, row_count(engine, accounts), row_count(engine, sessions)) == ([], 1, 2)


def a_transaction_waits_for_a_row(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_locks JOIN pg_stat_activity USING (pid)"
                " WHERE locktype = 'transactionid' AND NOT granted AND datname = current_database()"
            )
        ).scalar_one()


def cut_every_other_connection(engine):
    with engine.connect() as cutter:
        cutter.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        )
        cutter.commit()


@pytest.fixture
def cut_connection(engine):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        cut_every_other_connection(engine)
        yield connection


class TestAnUnreachableDatabase:
    @pytest.fixture
    def nowhere(self):
        engine = create_store_engine("postgresql://nobody:none@127.0.0.1:1/none")
        yield PostgresSignInStores(engine, audit=RecordingAudit())
        engine.dispose()

    def test_raises_store_unavailable_when_a_session_call_cannot_open_its_transaction(self, nowhere):
        with pytest.raises(StoreUnavailableError):
            nowhere.sessions.load("session-unknown")

    def test_raises_store_unavailable_when_a_sign_in_entry_cannot_open_its_transaction(self, nowhere):
        with pytest.raises(StoreUnavailableError), nowhere.transaction():
            pytest.fail("the entry opened")

    @pytest.mark.parametrize(
        "call",
        [lambda entry: entry.accounts.get(SUBJECT), lambda entry: entry.sessions.load("session-unknown")],
        ids=["an account call", "a session call"],
    )
    def test_raises_store_unavailable_from_a_call_after_the_connection_was_cut(self, engine, stores, call):
        def cut_then_call():
            with stores.transaction() as entry:
                cut_every_other_connection(engine)
                call(entry)

        with pytest.raises(StoreUnavailableError):
            cut_then_call()

    @pytest.mark.parametrize(
        "call",
        [
            lambda accounts: accounts.get(SUBJECT),
            lambda accounts: accounts.create_for_subject(SUBJECT, "Anna", "user", AccountKind.PERSON),
            lambda accounts: accounts.set_role(SUBJECT, "admin"),
            lambda accounts: accounts.set_kind(SUBJECT, AccountKind.AGENT),
        ],
        ids=["get", "create_for_subject", "set_role", "set_kind"],
    )
    def test_raises_store_unavailable_from_an_account_call_on_a_cut_connection(self, cut_connection, call):
        with pytest.raises(StoreUnavailableError):
            call(PostgresAccounts(cut_connection))

    def test_raises_store_unavailable_when_a_sign_in_entry_cannot_commit(self, engine, stores):
        with pytest.raises(StoreUnavailableError), stores.transaction():
            cut_every_other_connection(engine)

    def test_raises_store_unavailable_when_a_session_call_cannot_commit(self, engine):
        @contextmanager
        def cutting_before_the_commit():
            with engine.begin() as connection:
                yield connection
                cut_every_other_connection(engine)

        with pytest.raises(StoreUnavailableError):
            PostgresSessionRecords(cutting_before_the_commit).delete("session-unknown")


class TestADeadlock:
    def test_raises_session_store_error_not_store_unavailable(self, engine, stores):
        first = sign_in(stores).id
        second = sign_in(stores).id
        failures = []

        def entry_that_locks_the_second_then_the_first():
            try:
                with stores.transaction() as entry:
                    entry.sessions.touch(second, expires_at=NOW + LIFETIME)
                    entry.sessions.touch(first, expires_at=NOW + LIFETIME)
            except Exception as failure:
                failures.append(failure)

        def lock(connection, session_id):
            connection.execute(
                sessions.update()
                .where(sessions.c.id_hash == hashlib.sha256(session_id.encode()).hexdigest())
                .values(expires_at=NOW)
            )

        with engine.begin() as holder:
            lock(holder, first)
            thread = threading.Thread(target=entry_that_locks_the_second_then_the_first)
            thread.start()
            deadline = time.monotonic() + WAIT_DEADLINE_SECONDS
            while not a_transaction_waits_for_a_row(engine):
                assert time.monotonic() < deadline
                time.sleep(POLL_SECONDS)
            lock(holder, second)
            thread.join(WAIT_DEADLINE_SECONDS)

        assert [type(failure) for failure in failures] == [SessionStoreError]


class TestAnAccount:
    def test_changes_its_role_and_its_kind_and_keeps_the_rest(self, stores):
        sign_in(stores)

        with stores.transaction() as entry:
            entry.accounts.set_role(SUBJECT, "admin")
            changed = entry.accounts.set_kind(SUBJECT, AccountKind.AGENT)

        assert (changed.id, changed.username, changed.role, changed.kind) == (
            SUBJECT,
            "Anna",
            "admin",
            AccountKind.AGENT,
        )


class TestTheStoredSession:
    def test_has_the_hash_of_the_cookies_id_as_its_id_column_and_the_raw_id_nowhere(self, engine, stores):
        session = sign_in(stores)

        with engine.connect() as connection:
            row = connection.execute(select(sessions)).one()
        assert row.id_hash == hashlib.sha256(session.id.encode()).hexdigest()
        assert session.id not in {value for value in row if isinstance(value, str)}

    def test_is_loaded_with_its_raw_id_its_account_and_its_tokens(self, stores):
        session = sign_in(stores)

        loaded = stores.sessions.load(session.id)

        assert loaded is not None
        assert (loaded.id, loaded.user.id, loaded.user.kind, loaded.account_language) == (
            session.id,
            SUBJECT,
            AccountKind.PERSON,
            "de",
        )
        assert (loaded.created_at, loaded.expires_at) == (NOW, NOW + LIFETIME)
        assert (loaded.refresh_token, loaded.id_token) == (SecretStr("refresh-token"), SecretStr("id-token"))

    def test_without_tokens_is_loaded_without_tokens(self, stores):
        with stores.transaction() as entry:
            entry.accounts.create_for_subject(SUBJECT, "Anna", "user", AccountKind.PERSON)
            session = entry.sessions.create(
                SUBJECT,
                session_id="session-without-tokens",
                now=NOW,
                expires_at=NOW + LIFETIME,
                refresh_token=None,
                id_token=None,
                account_language=None,
            )

        loaded = stores.sessions.load(session.id)

        assert (loaded.refresh_token, loaded.id_token, loaded.account_language) == (None, None, None)

    def test_is_not_found_by_the_text_of_the_stored_hash(self, engine, stores):
        sign_in(stores)
        with engine.connect() as connection:
            stored_hash = connection.execute(select(sessions.c.id_hash)).scalar_one()

        assert stores.sessions.load(stored_hash) is None

    def test_is_loaded_after_it_expired_for_the_gate_to_decide(self, stores):
        session = sign_in(stores, created_at=NOW - 2 * LIFETIME)

        assert stores.sessions.load(session.id) is not None

    def test_is_renewed_in_place_by_a_touch_that_leaves_its_tokens(self, stores):
        session = sign_in(stores)

        renewed = stores.sessions.touch(session.id, expires_at=NOW + 2 * LIFETIME)

        loaded = stores.sessions.load(session.id)
        assert (renewed, loaded.expires_at, loaded.refresh_token) == (
            True,
            NOW + 2 * LIFETIME,
            SecretStr("refresh-token"),
        )

    def test_of_another_app_is_seen_renewed_and_ended_by_the_app_asked_next(self, engine, audit):
        first, second = (PostgresSignInStores(engine, audit=audit) for _ in range(2))
        session = sign_in(first)

        first.sessions.touch(session.id, expires_at=NOW + 2 * LIFETIME)
        seen_renewed = second.sessions.load(session.id).expires_at
        first.sessions.delete(session.id)

        assert (seen_renewed, second.sessions.load(session.id)) == (NOW + 2 * LIFETIME, None)

    def test_has_its_refresh_token_replaced_in_place(self, stores):
        session = sign_in(stores)

        replaced = stores.sessions.replace_refresh_token(session.id, refresh_token=SecretStr("rotated"))

        assert (replaced, stores.sessions.load(session.id).refresh_token) == (True, SecretStr("rotated"))

    def test_that_ends_with_its_delete_leaves_the_account_and_a_delete_of_an_unknown_id_does_nothing(
        self, engine, stores
    ):
        session = sign_in(stores)

        stores.sessions.delete("an-id-nobody-holds")
        stores.sessions.delete(session.id)

        assert (row_count(engine, sessions), row_count(engine, accounts)) == (0, 1)


class TestTheExpirySweep:
    def test_deletes_the_expired_sessions_and_keeps_the_live_ones_and_a_second_run_deletes_none(self, engine, audit):
        first_app, second_app = (PostgresSignInStores(engine, audit=audit) for _ in range(2))
        expired = sign_in(first_app, created_at=NOW - 2 * LIFETIME)
        live = sign_in(first_app, created_at=NOW)

        deleted_by_first = first_app.sessions.delete_expired(NOW)
        deleted_by_second = second_app.sessions.delete_expired(NOW)

        assert (deleted_by_first, deleted_by_second) == (1, 0)
        assert (first_app.sessions.load(expired.id), first_app.sessions.load(live.id) is not None) == (None, True)
