from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

MIGRATIONS_DIRECTORY: Final = Path(__file__).parent / "migrations"
# Serialises concurrent `skat migrate` runs; any constant shared by all of them does.
MIGRATION_LOCK_KEY: Final = 7_184_203_551
POSTGRES_DRIVER: Final = "postgresql+psycopg"
# Bounds how long a connection attempt waits for a database that is down or silent; libpq takes whole seconds
# and reads anything below two as two.
STORE_CONNECT_TIMEOUT_SECONDS: Final = 5
# Bounds how long the health check waits on a database that connected and then stops answering.
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


def _current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def require_head(engine: Engine) -> None:
    head = _head_revision()
    with engine.connect() as connection:
        current = _current_revision(connection)
    if current != head:
        raise DatabaseNotAtHeadError(
            f"The database is at revision {current or 'none'} but Skat needs {head}; run skat migrate first"
        )


def database_health(engine: Engine) -> DatabaseHealth:
    """Whether the database serves a query and is at the newest migration; it raises on neither.

    The database's revision is read on every ask, because a rollout moves it while Skat runs; the newest revision
    is not, because it cannot change in the process.
    """
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('statement_timeout', :milliseconds, true)"),
                {"milliseconds": str(HEALTH_STATEMENT_TIMEOUT_MILLISECONDS)},
            )
            return DatabaseHealth(serves_queries=True, at_head=_current_revision(connection) == _head_revision())
    except SQLAlchemyError:
        return DatabaseHealth(serves_queries=False, at_head=False)
