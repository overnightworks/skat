import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from skat.store import migrate as migrate_module
from skat.store.migrate import (
    DatabaseNotAtHeadError,
    create_store_engine,
    database_health,
    migrate,
    require_head,
)

pytestmark = pytest.mark.postgres

WELL_PAST_THE_DEADLINE_SECONDS = 30


class TestRequireHead:
    def test_accepts_a_database_at_head(self, unmigrated_engine):
        migrate(unmigrated_engine)

        require_head(unmigrated_engine)

    def test_refuses_an_unmigrated_database_and_says_which_command_fixes_it(self, unmigrated_engine):
        with pytest.raises(DatabaseNotAtHeadError, match="skat migrate"):
            require_head(unmigrated_engine)

    def test_refuses_a_database_at_an_older_revision(self, unmigrated_engine):
        migrate(unmigrated_engine)
        with unmigrated_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'older'"))

        with pytest.raises(DatabaseNotAtHeadError, match="older"):
            require_head(unmigrated_engine)

    def test_refuses_a_database_that_holds_a_second_revision_besides_the_newest(self, unmigrated_engine):
        migrate(unmigrated_engine)
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('older')"))

        with pytest.raises(DatabaseNotAtHeadError, match="older"):
            require_head(unmigrated_engine)


class TestDatabaseHealth:
    def test_a_database_at_head_serves_and_is_ready(self, unmigrated_engine):
        migrate(unmigrated_engine)

        health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.at_head, health.ready) == (True, True, True)

    def test_an_unmigrated_database_serves_but_is_not_at_head(self, unmigrated_engine):
        health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.at_head, health.ready) == (True, False, False)

    def test_a_database_at_an_older_revision_is_not_at_head(self, unmigrated_engine):
        migrate(unmigrated_engine)
        with unmigrated_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'older'"))

        assert database_health(unmigrated_engine).ready is False

    def test_a_database_that_holds_a_second_revision_besides_the_newest_is_not_at_head_and_raises_nothing(
        self, unmigrated_engine
    ):
        migrate(unmigrated_engine)
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('older')"))

        health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.at_head, health.ready) == (True, False, False)

    def test_the_answer_follows_the_database_as_it_is_migrated_between_two_asks(self, unmigrated_engine):
        before = database_health(unmigrated_engine)

        migrate(unmigrated_engine)

        assert (before.ready, database_health(unmigrated_engine).ready) == (False, True)

    def test_a_database_nothing_listens_on_neither_serves_nor_raises(self):
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        engine = create_store_engine(f"postgresql://skat:secret@127.0.0.1:{port}/skat")

        health = database_health(engine)

        engine.dispose()
        assert (health.serves_queries, health.at_head, health.ready) == (False, False, False)

    def test_a_database_that_accepts_and_never_answers_gives_up_instead_of_hanging(self, monkeypatch):
        monkeypatch.setattr(migrate_module, "STORE_CONNECT_TIMEOUT_SECONDS", 2)
        with socket.socket() as silent:
            silent.bind(("127.0.0.1", 0))
            silent.listen()
            engine = create_store_engine(f"postgresql://skat:secret@127.0.0.1:{silent.getsockname()[1]}/skat")

            health = database_health(engine)

            engine.dispose()
        assert health.ready is False

    def test_a_database_that_connected_and_then_stops_answering_is_given_up_on_at_the_deadline(
        self, database_url, relay_in_front_of, monkeypatch
    ):
        monkeypatch.setattr(migrate_module, "HEALTH_DEADLINE_SECONDS", 1)
        relay = relay_in_front_of(database_url)
        engine = create_store_engine(relay.url)
        relay.stall()
        executor = ThreadPoolExecutor(max_workers=1)

        try:
            health = executor.submit(database_health, engine).result(timeout=WELL_PAST_THE_DEADLINE_SECONDS)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        assert (health.serves_queries, health.ready) == (False, False)

    def test_a_database_whose_hostname_never_resolves_is_given_up_on_at_the_deadline(self, monkeypatch):
        monkeypatch.setattr(migrate_module, "HEALTH_DEADLINE_SECONDS", 1)
        resolver_released = threading.Event()
        monkeypatch.setattr(socket, "getaddrinfo", lambda *_arguments, **_keywords: resolver_released.wait())
        engine = create_store_engine("postgresql://skat:secret@database.invalid:5432/skat")
        executor = ThreadPoolExecutor(max_workers=1)

        try:
            health = executor.submit(database_health, engine).result(timeout=WELL_PAST_THE_DEADLINE_SECONDS)
        finally:
            resolver_released.set()
            executor.shutdown(wait=False, cancel_futures=True)

        assert (health.serves_queries, health.ready) == (False, False)

    def test_a_database_that_stops_answering_after_it_connected_gives_up_instead_of_hanging(
        self, unmigrated_engine, monkeypatch
    ):
        migrate(unmigrated_engine)
        monkeypatch.setattr(migrate_module, "HEALTH_STATEMENT_TIMEOUT_MILLISECONDS", 300)
        with unmigrated_engine.connect() as locker:
            locker.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))

            health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.ready) == (False, False)
