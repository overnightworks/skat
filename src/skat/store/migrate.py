import asyncio
import os
import socket
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

import psycopg
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url

MIGRATIONS_DIRECTORY: Final = Path(__file__).parent / "migrations"
# Serialises concurrent `skat migrate` runs; any constant shared by all of them does.
MIGRATION_LOCK_KEY: Final = 7_184_203_551
POSTGRES_DRIVER: Final = "postgresql+psycopg"
# Bounds how long a connection attempt waits for a database that is down or silent; libpq takes whole seconds
# and reads anything below two as two.
STORE_CONNECT_TIMEOUT_SECONDS: Final = 5
# Bounds the whole health check, connecting and closing included, on a database that is down, silent or stops
# answering after it connected; the client gives up, because a server that does not answer cannot time itself out.
HEALTH_DEADLINE_SECONDS: Final = 5
# Bounds the work the health check leaves on a database that is slow but answering.
HEALTH_STATEMENT_TIMEOUT_MILLISECONDS: Final = 2_000


class DatabaseNotAtHeadError(Exception):
    """The database is not at the newest migration; the message says which revision it holds."""


@dataclass(frozen=True)
class DatabaseHealth:
    serves_queries: bool
    at_head: bool

    @property
    def ready(self) -> bool:
        return self.serves_queries and self.at_head


def create_store_engine(database_url: str) -> Engine:
    """An engine on psycopg 3, whichever Postgres scheme the URL names."""
    return create_engine(
        make_url(database_url).set(drivername=POSTGRES_DRIVER),
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


def _current_revisions(connection: Connection) -> tuple[str, ...]:
    return MigrationContext.configure(connection).get_current_heads()


def require_head(engine: Engine) -> None:
    head = _head_revision()
    with engine.connect() as connection:
        current = _current_revisions(connection)
    if current != (head,):
        raise DatabaseNotAtHeadError(
            f"The database is at revision {', '.join(current) or 'none'} but Skat needs {head}; run skat migrate first"
        )


def _hang_up(connection: psycopg.AsyncConnection) -> None:
    """Ends the exchange on the connection's socket, so that a query waiting on it fails at once.

    Cancelling the waiting task instead would make psycopg ask the unresponsive server to cancel the query and wait
    on it for seconds more.
    """
    with socket.socket(fileno=os.dup(connection.pgconn.socket)) as duplicate:
        duplicate.shutdown(socket.SHUT_RDWR)


async def _read_current_revisions(engine: Engine) -> tuple[str, ...]:
    """The revisions the database holds, none while it is unmigrated, within the health deadline.

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
        cursor = await connection.execute("SELECT version_num FROM alembic_version")
        return tuple(version for (version,) in await cursor.fetchall())
    except psycopg.errors.UndefinedTable:
        return ()
    finally:
        hang_up.cancel()
        await connection.close()


def database_health(engine: Engine) -> DatabaseHealth:
    """Whether the database serves a query and is at the newest migration; it raises on neither and returns within
    the health deadline.

    The probe opens a connection of its own, so that neither the engine's pool (its pre-ping, a checkout waiting for
    a free connection) nor a hung server can hold it past the deadline. The database's revision is read on every
    ask, because a rollout moves it while Skat runs; the newest revision is not, because it cannot change in the
    process.
    """
    try:
        current = asyncio.run(_read_current_revisions(engine))
    except psycopg.Error, TimeoutError:
        return DatabaseHealth(serves_queries=False, at_head=False)
    return DatabaseHealth(serves_queries=True, at_head=current == (_head_revision(),))
