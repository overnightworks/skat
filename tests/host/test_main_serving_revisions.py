"""A process of one release keeps serving after a newer release's `skat migrate` ran on the database, as long as the
database still lists its revision as served, and turns unready, loudly, once it does not; a process that starts
needs its revision listed."""

import secrets
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url

from skat.store.migrate import READINESS_REUSE_SECONDS, create_store_engine
from skat.store.sign_in import PostgresSignInStores
from skat.web.constants import HEALTH_PATH
from skat.web.sign_in import LoggingAuditSink, build_sign_in_configs
from skat.web.tables import TABLES_PATH
from tests.support.in_memory_stores import in_process_rate_limits
from tests.support.migrations import FixtureRevision, release_source
from tests.support.postgres import created_database
from tests.support.redis import fresh_database_url
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN, build_sign_in_settings
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import CHECKOUT_SOURCE, SkatProcess, migrate_as_release

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

EXPAND = ("CREATE TABLE added_by_a_newer_release (id integer PRIMARY KEY)",)
ANOTHER_EXPAND = ("CREATE TABLE added_by_a_later_release (id integer PRIMARY KEY)",)
WELL_PAST_THE_REUSE_SECONDS = 3 * READINESS_REUSE_SECONDS
UNREADY_DEADLINE_SECONDS = 10


class Deployment:
    """One database, the releases of Skat that run on it (this checkout's, and newer ones that ship further
    migrations), and the processes started from them.
    """

    def __init__(self, directory, database_url: str) -> None:
        redis_url = fresh_database_url()
        self.sign_in = build_sign_in_settings(
            directory,
            database_url=make_url(database_url).set(drivername="postgresql", password=None).render_as_string(),
            redis_url=redis_url,
        )
        self._directory = directory
        self.engine = create_store_engine(database_url)
        self.releases = {
            "checkout": CHECKOUT_SOURCE,
            "newer": release_source(directory / "newer", FixtureRevision("newer", EXPAND)),
            "later": release_source(
                directory / "later", FixtureRevision("newer", EXPAND), FixtureRevision("later", ANOTHER_EXPAND)
            ),
        }
        self._processes: list[SkatProcess] = []

    def start(self, release: str) -> SkatProcess:
        process = SkatProcess(
            self.sign_in.environment, self._directory / f"pod-{len(self._processes)}.log", self.releases[release]
        )
        self._processes.append(process)
        process.start()
        return process

    def migrate_as(self, release: str) -> None:
        migrate_as_release(self.sign_in.environment, self.releases[release])

    def table_opened_by(self, process: SkatProcess) -> int:
        stores = PostgresSignInStores(self.engine, audit=LoggingAuditSink())
        config = build_sign_in_configs(self.sign_in.settings, in_process_rate_limits()).web_auth
        member = seed_member(stores, config)
        opened = process.request(
            "POST",
            TABLES_PATH,
            cookie=cookie_header(member.set_cookie_headers),
            json={"command_id": secrets.token_hex(8), "series_length": 3},
            origin=TEST_PUBLIC_ORIGIN,
        )
        return opened.status_code

    def stop(self) -> None:
        for process in self._processes:
            process.kill()
        self.engine.dispose()


@pytest.fixture
def deployment(postgres_template, tmp_path) -> Iterator[Deployment]:
    for name in ("newer", "later"):
        (tmp_path / name).mkdir()
    with created_database(postgres_template) as database_url:
        running = Deployment(tmp_path, database_url)
        try:
            yield running
        finally:
            running.stop()


@pytest.fixture
def checkout_process(deployment) -> SkatProcess:
    """The process of this checkout's release, serving before any newer release migrates."""
    return deployment.start("checkout")


class TestAProcessWhoseRevisionTheDatabaseStillServes:
    def test_stays_ready_and_serves_a_table_after_the_newer_release_migrated_the_database(
        self, deployment, checkout_process
    ):
        deployment.migrate_as("newer")

        assert checkout_process.stays_ready_for(WELL_PAST_THE_REUSE_SECONDS)
        assert deployment.table_opened_by(checkout_process) == 200

    @pytest.mark.parametrize("joining", ["newer", "checkout"])
    def test_is_joined_by_a_process_that_starts_after_the_migration(self, deployment, checkout_process, joining):
        deployment.migrate_as("newer")

        started = deployment.start(joining)

        assert started.request("GET", HEALTH_PATH).status_code == 200


class TestAProcessWhoseRevisionTheDatabaseNoLongerServes:
    def test_turns_unready_and_logs_why_once_two_newer_releases_have_migrated_the_database(
        self, deployment, checkout_process
    ):
        deployment.migrate_as("newer")
        deployment.migrate_as("later")

        assert checkout_process.becomes_unready_within(UNREADY_DEADLINE_SECONDS)
        (changed,) = checkout_process.log_lines("database_readiness.changed")
        assert (changed["was"], changed["now"]) == ("ready", "revision_not_served")

    def test_is_not_joined_by_a_process_that_starts_after_the_migration(self, deployment):
        deployment.migrate_as("newer")
        deployment.migrate_as("later")

        with pytest.raises(AssertionError, match="skat migrate"):
            deployment.start("checkout")
