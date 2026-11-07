import threading

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from skat.store.migrate import DatabaseNotAtHeadError, create_store_engine, migrate, require_head
from skat.store.tables import metadata

pytestmark = pytest.mark.postgres


@pytest.fixture
def engine(unmigrated_database_url):
    engine = create_store_engine(unmigrated_database_url)
    yield engine
    engine.dispose()


def table_names(engine):
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_migrating_an_empty_database_creates_tables_chairs_and_receipts(engine):
    migrate(engine)

    assert table_names(engine) == {"tables", "chairs", "receipts"}


def test_the_migrated_schema_is_the_one_the_store_writes_to(engine):
    migrate(engine)

    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


def test_migrating_twice_changes_nothing(engine):
    migrate(engine)
    with engine.connect() as connection:
        before = connection.execute(text("SELECT version_num FROM alembic_version")).all()

    migrate(engine)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).all() == before
    assert table_names(engine) == {"tables", "chairs", "receipts"}


def test_two_migrations_at_once_serialise_and_both_succeed(unmigrated_database_url):
    engines = [create_store_engine(unmigrated_database_url) for _ in range(2)]
    failures: list[BaseException] = []
    start = threading.Barrier(2)

    def run(engine):
        start.wait()
        try:
            migrate(engine)
        except BaseException as failure:
            failures.append(failure)

    threads = [threading.Thread(target=run, args=(engine,)) for engine in engines]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    with engines[0].connect() as connection:
        assert len(connection.execute(text("SELECT version_num FROM alembic_version")).all()) == 1
    for engine in engines:
        engine.dispose()


class TestRequireHead:
    def test_accepts_a_database_at_head(self, engine):
        migrate(engine)

        require_head(engine)

    def test_refuses_an_unmigrated_database_and_says_which_command_fixes_it(self, engine):
        with pytest.raises(DatabaseNotAtHeadError, match="skat migrate"):
            require_head(engine)

    def test_refuses_a_database_at_an_older_revision(self, engine):
        migrate(engine)
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'older'"))

        with pytest.raises(DatabaseNotAtHeadError, match="older"):
            require_head(engine)
