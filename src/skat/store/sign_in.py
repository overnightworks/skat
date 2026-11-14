from contextlib import contextmanager, nullcontext
from typing import TYPE_CHECKING

from sqlalchemy import text
from webauth.ports import SignInStores

from skat.store.accounts import PostgresAccounts
from skat.store.migrate import SIGN_IN_LOCK_KEY
from skat.store.sessions import PostgresSessionRecords

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy import Engine
    from webauth.ports import AccountEvent, AuditSink

__all__ = ["PostgresSignInStores"]


class _DeferredAudit:
    """Holds an entry's events until its writes are done, so an entry that fails reports none."""

    def __init__(self) -> None:
        self._events: list[AccountEvent] = []

    def account_event(self, event: AccountEvent) -> None:
        self._events.append(event)

    def report_to(self, sink: AuditSink) -> None:
        for event in self._events:
            sink.account_event(event)


class PostgresSignInTransaction:
    """One sign-in entry: a database transaction under a Postgres advisory lock that every entry of every app on the
    database takes first, so entries run one at a time across pods.

    The entry's events reach the sink as its last step, still inside the transaction: a sink that fails rolls the
    entry back with it, and an entry that raises reports no event.
    """

    def __init__(self, engine: Engine, audit: AuditSink) -> None:
        self._engine = engine
        self._audit = audit

    @contextmanager
    def __call__(self) -> Generator[SignInStores]:
        deferred = _DeferredAudit()
        with self._engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SIGN_IN_LOCK_KEY})
            yield SignInStores(
                accounts=PostgresAccounts(connection),
                sessions=PostgresSessionRecords(lambda: nullcontext(connection)),
                audit=deferred,
            )
            deferred.report_to(self._audit)


class PostgresSignInStores:
    """Skat's sessions and sign-in entry over one engine: `sessions` for the session gate, one transaction per call,
    and `transaction` for the sign-in routes.
    """

    def __init__(self, engine: Engine, *, audit: AuditSink) -> None:
        self.sessions = PostgresSessionRecords(engine.begin)
        self.transaction = PostgresSignInTransaction(engine, audit)
