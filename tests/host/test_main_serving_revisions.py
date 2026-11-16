"""A process keeps serving after another release migrated the database as long as the database still lists its
revision as served, and turns unready, loudly, once it does not; a process that starts needs its revision listed."""

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
from tests.support.migrations import FixtureRevision, upgrade_to, write_revisions
from tests.support.postgres import created_database
from tests.support.redis import fresh_database_url
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN, build_sign_in_settings
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import SkatProcess

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

EXPAND = ("CREATE TABLE added_by_a_newer_release (id integer PRIMARY KEY)",)
ANOTHER_EXPAND = ("CREATE TABLE added_by_a_later_release (id integer PRIMARY KEY)",)
WELL_PAST_THE_REUSE_SECONDS = 3 * READINESS_REUSE_SECONDS
UNREADY_DEADLINE_SECONDS = 10


class Release:
    """One database with a process of this checkout's revision serving on it, and the means to migrate it on."""

    def __init__(self, directory, database_url: str) -> None:
        redis_url = fresh_database_url()
        self.sign_in = build_sign_in_settings(
            directory,
            database_url=make_url(database_url).set(drivername="postgresql", password=None).render_as_string(),
            redis_url=redis_url,
        )
        self._directory = directory
        self.engine = create_store_engine(database_url)
        self._processes: list[SkatProcess] = []
        self.serving = self.new_process()
        self.serving.start()

    def new_process(self) -> SkatProcess:
        process = SkatProcess(self.sign_in.environment, self._directory / f"pod-{len(self._processes)}.log")
        self._processes.append(process)
        return process

    def migrate_on_to(self, revision: str) -> None:
        upgrade_to(self.engine, revision, extra_versions=self._directory)

    def table_opened_by_serving_process(self) -> int:
        stores = PostgresSignInStores(self.engine, audit=LoggingAuditSink())
        config = build_sign_in_configs(self.sign_in.settings, in_process_rate_limits()).web_auth
        member = seed_member(stores, config)
        opened = self.serving.request(
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
def release(postgres_template, tmp_path) -> Iterator[Release]:
    write_revisions(tmp_path, FixtureRevision("newer", EXPAND), FixtureRevision("later", ANOTHER_EXPAND))
    with created_database(postgres_template) as database_url:
        running = Release(tmp_path, database_url)
        try:
            yield running
        finally:
            running.stop()


class TestAProcessWhoseRevisionTheDatabaseStillServes:
    def test_stays_ready_and_serves_a_table_after_a_newer_release_migrated_the_database(self, release):
        release.migrate_on_to("newer")

        assert release.serving.stays_ready_for(WELL_PAST_THE_REUSE_SECONDS)
        assert release.table_opened_by_serving_process() == 200

    def test_is_joined_by_a_process_that_starts_after_the_migration(self, release):
        release.migrate_on_to("newer")
        joining = release.new_process()

        joining.start()

        assert joining.request("GET", HEALTH_PATH).status_code == 200


class TestAProcessWhoseRevisionTheDatabaseNoLongerServes:
    def test_turns_unready_and_logs_why_once_two_newer_releases_have_migrated_the_database(self, release):
        release.migrate_on_to("newer")
        release.migrate_on_to("later")

        assert release.serving.becomes_unready_within(UNREADY_DEADLINE_SECONDS)
        (changed,) = release.serving.log_lines("database_readiness.changed")
        assert (changed["was"], changed["now"]) == ("ready", "revision_not_served")

    def test_is_not_joined_by_a_process_that_starts_after_the_migration(self, release):
        release.migrate_on_to("newer")
        release.migrate_on_to("later")

        with pytest.raises(AssertionError, match="skat migrate"):
            release.new_process().start()
