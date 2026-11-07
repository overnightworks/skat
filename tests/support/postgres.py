import os
import secrets
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from skat.store.migrate import create_store_engine, migrate

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Engine

URL_ENVIRONMENT_VARIABLE = "SKAT_TEST_POSTGRES_URL"
DATABASE_NAME_BYTES = 8


def server_url() -> str:
    """The throwaway server's URL; `scripts/test_postgres.sh` and CI's service provide it."""
    url = os.environ.get(URL_ENVIRONMENT_VARIABLE)
    if not url:
        pytest.fail(f"{URL_ENVIRONMENT_VARIABLE} names no Postgres; run the tests through scripts/test_postgres.sh")
    return url


def _server_engine() -> Engine:
    return create_store_engine(server_url()).execution_options(isolation_level="AUTOCOMMIT")


def _database_url(name: str) -> str:
    return make_url(server_url()).set(database=name).render_as_string(hide_password=False)


def _new_name() -> str:
    return f"skat_{secrets.token_hex(DATABASE_NAME_BYTES)}"


@contextmanager
def created_database(template: str | None = None) -> Iterator[str]:
    """The URL of a new database, a copy of `template` when one is named; it is dropped afterwards."""
    name = _new_name()
    server = _server_engine()
    with server.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"' + ("" if template is None else f' TEMPLATE "{template}"')))
    try:
        yield _database_url(name)
    finally:
        with server.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


@contextmanager
def migrated_template() -> Iterator[str]:
    """A database migrated by Alembic once, named so that `created_database` copies it for each test."""
    with created_database() as url:
        engine = create_store_engine(url)
        migrate(engine)
        # A template cannot be copied while a connection to it is open.
        engine.dispose()
        yield make_url(url).database or ""
