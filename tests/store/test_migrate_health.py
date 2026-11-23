import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from skat.store import migrate as migrate_module
from skat.store.migrate import (
    RevisionNotServedError,
    create_store_engine,
    database_health,
    migrate,
    require_served_revision,
)
from tests.support.database_relay import READY_FOR_QUERY
from tests.support.migrations import head_revision, serve_only

pytestmark = pytest.mark.postgres

WELL_PAST_THE_DEADLINE_SECONDS = 30
CHUNK_BYTES = 1024
DECLINE_ENCRYPTION = b"N"
AUTHENTICATION_OK = b"R\x00\x00\x00\x08\x00\x00\x00\x00"


@pytest.fixture
def silent_database():
    """A listener that accepts connections and never answers, and an engine pointed at it."""
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        engine = create_store_engine(f"postgresql://skat:secret@127.0.0.1:{silent.getsockname()[1]}/skat")
        yield silent, engine
        engine.dispose()


def greet_and_go_silent(client: socket.socket) -> None:
    """Takes a client through its start as a server does, up to ready for a query, and answers nothing after it."""
    client.settimeout(WELL_PAST_THE_DEADLINE_SECONDS)
    client.recv(CHUNK_BYTES)  # the request to encrypt the connection
    client.sendall(DECLINE_ENCRYPTION)
    client.recv(CHUNK_BYTES)  # the start-up message
    client.sendall(AUTHENTICATION_OK + READY_FOR_QUERY)


class TestRequireServedRevision:
    def test_accepts_a_database_that_serves_the_head(self, unmigrated_engine):
        migrate(unmigrated_engine)

        require_served_revision(unmigrated_engine)

    def test_refuses_an_unmigrated_database_and_says_which_command_fixes_it(self, unmigrated_engine):
        with pytest.raises(RevisionNotServedError, match="skat migrate"):
            require_served_revision(unmigrated_engine)

    @pytest.mark.parametrize(
        ("served", "named"),
        [(("older", "newer"), "newer, older"), ((), "no revision")],
        ids=["other revisions, which it names", "no revision"],
    )
    def test_refuses_a_database_that_does_not_serve_the_head(self, unmigrated_engine, served, named):
        migrate(unmigrated_engine)
        serve_only(unmigrated_engine, *served)

        with pytest.raises(RevisionNotServedError, match=named):
            require_served_revision(unmigrated_engine)


class TestDatabaseHealth:
    def test_a_database_that_serves_the_head_serves_and_is_ready(self, unmigrated_engine):
        migrate(unmigrated_engine)

        health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.revision_served, health.ready) == (True, True, True)

    def test_an_unmigrated_database_serves_queries_but_not_the_revision(self, unmigrated_engine):
        health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.revision_served, health.ready) == (True, False, False)

    def test_a_database_that_serves_other_revisions_is_not_ready(self, unmigrated_engine):
        migrate(unmigrated_engine)
        serve_only(unmigrated_engine, "older")

        assert database_health(unmigrated_engine).ready is False

    def test_a_database_that_serves_the_head_beside_another_revision_is_ready_and_raises_nothing(
        self, unmigrated_engine
    ):
        migrate(unmigrated_engine)
        serve_only(unmigrated_engine, head_revision(), "newer")

        health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.revision_served, health.ready) == (True, True, True)

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
        assert (health.serves_queries, health.revision_served, health.ready) == (False, False, False)

    def test_a_database_that_accepts_and_never_answers_gives_up_instead_of_hanging(self, silent_database, monkeypatch):
        monkeypatch.setattr(migrate_module, "STORE_CONNECT_TIMEOUT_SECONDS", 2)
        _, engine = silent_database

        health = database_health(engine)

        assert health.ready is False

    def test_a_probe_the_deadline_cut_off_leaves_no_connection_open(self, silent_database, monkeypatch):
        monkeypatch.setattr(migrate_module, "HEALTH_DEADLINE_SECONDS", 1)
        silent, engine = silent_database

        database_health(engine)

        engine.dispose()
        client, _ = silent.accept()
        with client:
            client.settimeout(WELL_PAST_THE_DEADLINE_SECONDS)
            while client.recv(CHUNK_BYTES):
                continue

    def test_a_query_the_deadline_cut_off_leaves_no_connection_open(self, silent_database, monkeypatch):
        monkeypatch.setattr(migrate_module, "HEALTH_DEADLINE_SECONDS", 1)
        silent, engine = silent_database
        executor = ThreadPoolExecutor(max_workers=1)

        try:
            probe = executor.submit(database_health, engine)
            client, _ = silent.accept()
            with client:
                greet_and_go_silent(client)
                while client.recv(CHUNK_BYTES):
                    continue
            health = probe.result(timeout=WELL_PAST_THE_DEADLINE_SECONDS)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        assert (health.serves_queries, health.ready) == (False, False)

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
            locker.execute(text("LOCK TABLE serving_revisions IN ACCESS EXCLUSIVE MODE"))

            health = database_health(unmigrated_engine)

        assert (health.serves_queries, health.ready) == (False, False)
