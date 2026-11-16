import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from skat.store.migrate import migrate
from tests.support.migrations import FixtureRevision, head_revision, served_revisions, upgrade_to, write_revisions

pytestmark = pytest.mark.postgres

HEAD = "head"
EXPAND = ("SELECT 1",)
BROKEN = ("SELECT * FROM a_table_that_is_not_there",)


def expanding(revision):
    return FixtureRevision(revision, EXPAND)


def contracting(revision):
    return FixtureRevision(revision, EXPAND, contracts=True)


WINDOWS = {
    "an expanding step keeps the revision before beside the new one": (
        [expanding("p1")],
        {HEAD, "p1"},
    ),
    "a contracting first step keeps the revision before beside the new one": (
        [contracting("p1")],
        {HEAD, "p1"},
    ),
    "two expanding steps keep the revision before beside the newest": (
        [expanding("p1"), expanding("p2")],
        {HEAD, "p2"},
    ),
    "a contraction after another step in one run leaves the new revision alone": (
        [expanding("p1"), contracting("p2")],
        {"p2"},
    ),
    "a contraction in the middle of a run is seen and leaves the newest revision alone": (
        [expanding("p1"), contracting("p2"), expanding("p3")],
        {"p3"},
    ),
}


class TestTheRevisionsTheDatabaseServes:
    def test_a_fresh_database_serves_the_head_alone(self, unmigrated_engine):
        migrate(unmigrated_engine)

        assert served_revisions(unmigrated_engine) == {head_revision()}

    def test_a_migration_that_applies_nothing_leaves_them_as_they_are(self, engine):
        before = served_revisions(engine)

        migrate(engine)

        assert served_revisions(engine) == before == {head_revision()}

    @pytest.mark.parametrize(("revisions", "served"), WINDOWS.values(), ids=WINDOWS.keys())
    def test_after_a_migrate_they_are_the_window_the_steps_allow(self, engine, tmp_path, revisions, served):
        write_revisions(tmp_path, *revisions)

        upgrade_to(engine, revisions[-1].revision, extra_versions=tmp_path)

        assert served_revisions(engine) == {head_revision() if each == HEAD else each for each in served}

    def test_a_run_that_fails_midway_leaves_them_and_the_applied_steps_as_they_were(self, engine, tmp_path):
        write_revisions(tmp_path, expanding("p1"), FixtureRevision("p2", BROKEN))

        with pytest.raises(DBAPIError):
            upgrade_to(engine, "p2", extra_versions=tmp_path)

        with engine.connect() as connection:
            applied = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        assert (served_revisions(engine), applied) == ({head_revision()}, [head_revision()])
