import asyncio
import os
import socket
import time
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

import psycopg
import structlog
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, delete, insert, inspect, text
from sqlalchemy.engine import make_url

from skat.store.schema import serving_revisions

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from alembic.runtime.migration import MigrationInfo
    from alembic.script import Script

MIGRATIONS_DIRECTORY: Final = Path(__file__).parent / "migrations"
# Serialises concurrent `skat migrate` runs; any constant shared by all of them does.
MIGRATION_LOCK_KEY: Final = 7_184_203_551
# Serialises the sign-in entries of this app's pods on its database; any constant distinct from the migration key does.
SIGN_IN_LOCK_KEY: Final = 7_184_203_552
POSTGRES_DRIVER: Final = "postgresql+psycopg"
# Bounds how long a connection attempt waits for a database that is down or silent; libpq takes whole seconds
# and reads anything below two as two.
STORE_CONNECT_TIMEOUT_SECONDS: Final = 5
# Bounds the whole health check, connecting and closing included, on a database that is down, silent or stops
# answering after it connected; the client gives up, because a server that does not answer cannot time itself out.
HEALTH_DEADLINE_SECONDS: Final = 5
# Bounds the work the health check leaves on a database that is slow but answering.
HEALTH_STATEMENT_TIMEOUT_MILLISECONDS: Final = 2_000
# The time within which readiness follows the database, far below the period in which the edge probes: a verdict
# answers every ask until the time left after the patience has run from the start of its probe, and an unfinished
# probe is awaited for the patience, from its start, before its asks read unready.
READINESS_REUSE_SECONDS: Final = 1.0
READINESS_PATIENCE_SECONDS: Final = 0.5

log = structlog.get_logger()


class RevisionNotServedError(Exception):
    """The database does not list this process's revision as served; the message says which revisions it lists."""


class ReadinessVerdict(StrEnum):
    READY = "ready"
    UNREACHABLE = "unreachable"
    REVISION_NOT_SERVED = "revision_not_served"
    SLOW = "slow"


@dataclass(frozen=True)
class DatabaseHealth:
    serves_queries: bool
    revision_served: bool

    @property
    def ready(self) -> bool:
        return self.serves_queries and self.revision_served

    @property
    def verdict(self) -> ReadinessVerdict:
        if not self.serves_queries:
            return ReadinessVerdict.UNREACHABLE
        return ReadinessVerdict.READY if self.revision_served else ReadinessVerdict.REVISION_NOT_SERVED


def create_store_engine(database_url: str) -> Engine:
    """An engine on psycopg 3, whichever Postgres scheme the URL names. Statement parameters stay out of error text,
    because a failed write of a session carries its tokens as parameters.
    """
    return create_engine(
        make_url(database_url).set(drivername=POSTGRES_DRIVER),
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": STORE_CONNECT_TIMEOUT_SECONDS},
    )


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    return config


def migrate(engine: Engine, operator_account_id: str | None = None) -> None:
    """Bring the database to head; concurrent runs wait for one another on a Postgres advisory lock. The operator's
    account id, when given, is the owner of the rule set a migration installs for him.
    """
    config = _alembic_config()
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        connection.commit()
        try:
            config.attributes["connection"] = connection
            config.attributes["operator_account_id"] = operator_account_id
            command.upgrade(config, "head")
        finally:
            connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            connection.commit()


@cache
def _head_revision() -> str | None:
    """The newest revision, which the migration files fix for the life of the process."""
    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def declares_contraction(script: Script) -> bool:
    """Whether the revision's file declares `CONTRACTS = True`, which exempts it from the check that migrations only
    expand and makes `ServingWindow` count it as a contraction.
    """
    return bool(getattr(script.module, "CONTRACTS", False))


@dataclass(frozen=True)
class AppliedStep:
    revision: str
    down_revision: str | None
    contracts: bool


class ServingWindow:
    """The revisions a `skat migrate` leaves served, which it works out from the steps it applies in its one
    transaction (`step_applied` sees each) and writes in that same transaction (`record`), so that a step that fails
    leaves them as they were.

    Steps that only expand keep the revision the database was at beside the new one, because code of that revision
    still reads the schema; that window of one release back is the most a release may rely on. A step that declares
    `CONTRACTS = True` is exempt from the check that migrations only expand, and drops only what the release before
    it no longer reads. The window knows steps, not releases, so a contracting step must be the first migration of
    its release: a contraction that is not the first step of the run is taken to skip a release, and the database
    then serves the new revision alone, so that processes of the release before turn unready too. A fresh database
    serves its head, and a run that applies no step changes nothing.
    """

    def __init__(self) -> None:
        self._revision_before: str | None = None
        self._steps: list[AppliedStep] = []

    def begins_at(self, heads: Collection[str]) -> None:
        self._revision_before = next(iter(heads), None)

    def step_applied(self, *, step: MigrationInfo, **_: object) -> None:
        """Alembic's `on_version_apply` hook, which it calls by keyword."""
        if step.is_upgrade:
            self._steps.append(
                AppliedStep(
                    revision=step.up_revision_ids[0],
                    down_revision=step.down_revision_ids[0] if step.down_revision_ids else None,
                    contracts=declares_contraction(step.up_revision),
                )
            )

    def _served(self) -> frozenset[str] | None:
        """The revisions to serve after the run, or None when it applied no step."""
        if not self._steps:
            return None
        newest = self._steps[-1].revision
        skipped_past_a_contraction = any(
            step.contracts and step.down_revision != self._revision_before for step in self._steps
        )
        if self._revision_before is None or skipped_past_a_contraction:
            return frozenset({newest})
        return frozenset({self._revision_before, newest})

    def record(self, connection: Connection) -> None:
        """Writes the window once the table exists; a run that stops below the revision that creates it writes none."""
        served = self._served()
        if served is None or not inspect(connection).has_table(serving_revisions.name):
            return
        connection.execute(delete(serving_revisions))
        connection.execute(insert(serving_revisions), [{"revision": revision} for revision in sorted(served)])


def require_served_revision(engine: Engine) -> None:
    head = _head_revision()
    served = _run_within_deadline(engine)
    if head not in served:
        raise RevisionNotServedError(
            f"The database serves {', '.join(sorted(served)) or 'no revision'} but Skat is at {head}; run skat migrate"
            " if the database is behind, and start the release the database serves if it is ahead"
        )


def _hang_up(connection: psycopg.AsyncConnection) -> None:
    """Ends the exchange on the connection's socket, so that a query waiting on it fails at once.

    Cancelling the waiting task instead would make psycopg ask the unresponsive server to cancel the query and wait
    on it for seconds more.
    """
    with socket.socket(fileno=os.dup(connection.pgconn.socket)) as duplicate:
        duplicate.shutdown(socket.SHUT_RDWR)


async def _read_served_revisions(engine: Engine) -> frozenset[str]:
    """The revisions the database lists as served, none while it is unmigrated, within the health deadline.

    The connection is closed, not rolled back, because a rollback would wait on the server again; closing ends the
    session and so its transaction.
    """
    _, parameters = engine.dialect.create_connect_args(engine.url)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + HEALTH_DEADLINE_SECONDS
    async with asyncio.timeout_at(deadline):
        connection = await psycopg.AsyncConnection.connect(
            **parameters,
            connect_timeout=STORE_CONNECT_TIMEOUT_SECONDS,
            options=f"-c statement_timeout={HEALTH_STATEMENT_TIMEOUT_MILLISECONDS}",
        )
    hang_up = loop.call_at(deadline, _hang_up, connection)
    try:
        cursor = await connection.execute("SELECT revision FROM serving_revisions")
        return frozenset(revision for (revision,) in await cursor.fetchall())
    except psycopg.errors.UndefinedTable:
        return frozenset()
    finally:
        hang_up.cancel()
        await connection.close()


def _run_within_deadline(engine: Engine) -> frozenset[str]:
    """Runs the probe on a loop of its own and closes the loop without waiting for the resolver thread.

    A hostname lookup runs in the loop's executor, and no cancellation reaches a lookup already running; the
    lookup finishes on its own, however long the system resolver takes. `asyncio.run` would wait for it, up to
    five minutes, so the loop is closed instead, which leaves the executor to wind down once the lookup returns.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_read_served_revisions(engine))
    finally:
        loop.close()


def database_health(engine: Engine) -> DatabaseHealth:
    """Whether the database serves a query and lists this process's revision as served; it raises on neither and
    returns within the health deadline.

    The probe opens a connection of its own, so that neither the engine's pool (its pre-ping, a checkout waiting for
    a free connection) nor a hung server can hold it past the deadline. The revisions served are read on every
    ask, because a rollout moves the revisions served while Skat runs; the process's own revision is not, because it
    cannot change in the process.
    """
    try:
        served = _run_within_deadline(engine)
    except psycopg.Error, TimeoutError:
        return DatabaseHealth(serves_queries=False, revision_served=False)
    return DatabaseHealth(serves_queries=True, revision_served=_head_revision() in served)


class ReadinessProbe:
    """The readiness verdict, computed by at most one probe at a time and following the database within
    `READINESS_REUSE_SECONDS`.

    A burst of asks costs one probe connection and one thread, never one per ask: an ask that arrives while a probe
    runs awaits that probe's verdict, but only until `READINESS_PATIENCE_SECONDS` after the probe started; a probe
    that has not answered by then reads unready, as slow, not after the health deadline. A verdict answers
    asks until the reuse time less the patience has run from the probe's start, because it read the database after
    that start; so a stop turns the verdict within the reuse time, whether the probe then answers or stalls. A
    verdict that differs from the previous one is logged once with its cause; a probe that answers ready after the
    patience stays slow, as its askers were told, and a stalled probe turns only a ready verdict to slow, so that a
    slow database logs one verdict and not one per probe. The first probe is compared with ready, which
    `require_served_revision` established before Skat served.
    """

    def __init__(self, probe: Callable[[], DatabaseHealth], *, clock: Callable[[], float] = time.monotonic) -> None:
        self._probe = probe
        self._clock = clock
        self._verdict = ReadinessVerdict.READY
        self._reusable_until: float | None = None
        self._started_at = 0.0
        self._running: asyncio.Task[bool] | None = None

    async def __call__(self) -> bool:
        if self._running is None:
            if self._reusable_until is not None and self._clock() < self._reusable_until:
                return self._verdict is ReadinessVerdict.READY
            self._started_at = self._clock()
            self._running = asyncio.create_task(self._refresh(self._started_at))
        running = self._running
        patience = self._started_at + READINESS_PATIENCE_SECONDS - self._clock()
        # `wait` leaves the probe running when its time is up or an asker is cancelled, for the others to await.
        await asyncio.wait({running}, timeout=max(patience, 0))
        if running.done():
            return running.result()
        if self._verdict is ReadinessVerdict.READY:
            self._record(ReadinessVerdict.SLOW)
        return False

    def _record(self, verdict: ReadinessVerdict) -> None:
        if verdict is not self._verdict:
            log.warning("database_readiness.changed", was=self._verdict.value, now=verdict.value)
            self._verdict = verdict

    async def _refresh(self, started_at: float) -> bool:
        try:
            health = await asyncio.to_thread(self._probe)
            self._reusable_until = started_at + READINESS_REUSE_SECONDS - READINESS_PATIENCE_SECONDS
            late = self._clock() - started_at > READINESS_PATIENCE_SECONDS
            verdict = ReadinessVerdict.SLOW if late and health.ready else health.verdict
            self._record(verdict)
            return verdict is ReadinessVerdict.READY
        finally:
            self._running = None
