from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

MIGRATIONS_DIRECTORY: Final = Path(__file__).parent / "migrations"
# Serialises concurrent `skat migrate` runs; any constant shared by all of them does.
MIGRATION_LOCK_KEY: Final = 7_184_203_551
POSTGRES_DRIVER: Final = "postgresql+psycopg"


class DatabaseNotAtHeadError(Exception):
    """The database is not at the newest migration; the message says which revision it holds."""


def create_store_engine(database_url: str) -> Engine:
    """An engine on psycopg 3, whichever Postgres scheme the URL names."""
    return create_engine(make_url(database_url).set(drivername=POSTGRES_DRIVER), pool_pre_ping=True)


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    return config


def migrate(engine: Engine) -> None:
    """Bring the database to head; concurrent runs wait for one another on a Postgres advisory lock."""
    config = _alembic_config()
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        connection.commit()
        try:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        finally:
            connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            connection.commit()


def require_head(engine: Engine) -> None:
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise DatabaseNotAtHeadError(
            f"The database is at revision {current or 'none'} but Skat needs {head}; run skat migrate first"
        )
