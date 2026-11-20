import re
import subprocess

import pytest
from sqlalchemy import Column, MetaData, Table, Text

from skat.store.migrate import MIGRATIONS_DIRECTORY
from skat.store.schema import held_back, metadata, one_of
from tests.support.migrations import FixtureRevision, has_revision, upgrade_to, write_revisions
from tests.support.schema_contractions import Admission, admissions, schema_facts, unreadable_by_the_release_before

pytestmark = pytest.mark.postgres

RELEASE_TAG_PATTERN = "v*"
VERSIONS = "versions"
REVISION_LINE = re.compile(r'^revision = "(?P<revision>\w+)"$', re.MULTILINE)
DOWN_REVISION_LINE = re.compile(r'^down_revision = "(?P<revision>\w+)"$', re.MULTILINE)

LISTS_A_AND_B = (
    "CREATE TABLE scratch (id integer PRIMARY KEY, status text, ending text,"
    " CONSTRAINT scratch_status_is_known CHECK (status IN ('a', 'b')))",
)
LISTS_A_B_AND_C_HELD_BACK = (
    "CREATE TABLE scratch (id integer PRIMARY KEY, status text, ending text,"
    " CONSTRAINT scratch_status_is_known CHECK (status IN ('a', 'b', 'c')),"
    " CONSTRAINT status_held_back CHECK (status <> ALL (ARRAY['c'])))",
)
WIDEN = (
    "ALTER TABLE scratch DROP CONSTRAINT scratch_status_is_known,"
    " ADD CONSTRAINT scratch_status_is_known CHECK (status IN ('a', 'b', 'c'))"
)
HOLD_BACK_C = "ALTER TABLE scratch ADD CONSTRAINT status_held_back CHECK (status <> ALL (ARRAY['c']))"
DROP_THE_HOLD_BACK = "ALTER TABLE scratch DROP CONSTRAINT status_held_back"
# `status <> 'c'` inside an OR says nothing about what a release may write.
ONLY_CONDITIONALLY_NOT_C = (
    "ALTER TABLE scratch ADD CONSTRAINT status_not_c_unless CHECK (status <> 'c' OR ending = 'x')"
)

STEPS_AFTER_THE_RELEASE_BEFORE = {
    "widens a list without a hold-back": (LISTS_A_AND_B, (WIDEN,), "status"),
    "widens a list and holds the new value back": (LISTS_A_AND_B, (WIDEN, HOLD_BACK_C), None),
    "widens a list beside an OR check that holds a <>": (LISTS_A_AND_B, (WIDEN, ONLY_CONDITIONALLY_NOT_C), "status"),
    "drops the hold-back the release before carried": (LISTS_A_B_AND_C_HELD_BACK, (DROP_THE_HOLD_BACK,), None),
    "widens a list again in the release that drops the hold-back": (
        LISTS_A_B_AND_C_HELD_BACK,
        (
            DROP_THE_HOLD_BACK,
            "ALTER TABLE scratch DROP CONSTRAINT scratch_status_is_known,"
            " ADD CONSTRAINT scratch_status_is_known CHECK (status IN ('a', 'b', 'c', 'd'))",
        ),
        "'d'",
    ),
}


@pytest.mark.parametrize(
    ("setup", "steps", "named"), STEPS_AFTER_THE_RELEASE_BEFORE.values(), ids=STEPS_AFTER_THE_RELEASE_BEFORE.keys()
)
def test_a_revision_that(engine, tmp_path, setup, steps, named):
    write_revisions(tmp_path, FixtureRevision("release_before", setup), FixtureRevision("next_release", steps))
    upgrade_to(engine, "release_before", extra_versions=tmp_path)
    before = schema_facts(engine)
    upgrade_to(engine, "next_release", extra_versions=tmp_path)

    found = unreadable_by_the_release_before(before, schema_facts(engine))

    assert found == [] if named is None else found and all(named in each for each in found)


def test_the_admissions_at_head_equal_those_of_a_database_built_from_the_metadata(engine, unmigrated_engine):
    metadata.create_all(unmigrated_engine)

    assert admissions(schema_facts(engine)) == admissions(schema_facts(unmigrated_engine))


def test_the_hold_back_helper_builds_a_check_the_reflection_reads_as_a_hold_back(unmigrated_engine):
    scratch = Table(
        "scratch", MetaData(), Column("status", Text), one_of("status", ("a", "b", "c"), "scratch_status_is_known")
    )
    scratch.append_constraint(held_back("status", ["c"]))
    scratch.metadata.create_all(unmigrated_engine)

    assert admissions(schema_facts(unmigrated_engine)) == {
        ("scratch", "status"): Admission(frozenset("abc"), frozenset("c"))
    }


def _git(*arguments: str) -> str:
    finished = subprocess.run(  # noqa: S603, S607 - git with the test's own arguments
        ["git", *arguments],  # noqa: S607
        cwd=MIGRATIONS_DIRECTORY,
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode:
        pytest.fail(f"git {' '.join(arguments)} failed: {finished.stderr.strip()}")
    return finished.stdout


def newest_of(tags: list[str]) -> str:
    """The newest release tag by version sort, `vYYYY.MM.DD.N` with N of any length."""
    if not tags:
        pytest.fail(
            "no release tag `v*` is fetched; fetch the newest with "
            "`git fetch --depth=1 origin tag $(git ls-remote --tags --refs --sort=-v:refname origin 'v*' | "
            "head -n 1 | sed 's|.*refs/tags/||')`"
        )
    return max(tags, key=lambda tag: [int(part) for part in tag.removeprefix("v").split(".")])


def require_revision(revision: str, tag: str) -> None:
    if not has_revision(revision):
        pytest.fail(f"this branch lacks revision {revision} of release {tag}; merge main into it")


def newest_revision_of(tag: str) -> str:
    """The revision no other migration of the release `tag` follows, read from the tag's own files."""
    files = _git("ls-tree", "--name-only", tag, f"{VERSIONS}/").split()
    contents = [_git("show", f"{tag}:./{name}") for name in files if name.endswith(".py")]
    revisions = {REVISION_LINE.search(each)["revision"] for each in contents if REVISION_LINE.search(each)}
    followed = {DOWN_REVISION_LINE.search(each)["revision"] for each in contents if DOWN_REVISION_LINE.search(each)}
    (newest,) = revisions - followed
    return newest


def test_a_release_writes_only_values_the_newest_release_tag_reads(unmigrated_engine, engine):
    tag = newest_of(_git("tag", "--list", RELEASE_TAG_PATTERN).split())
    revision = newest_revision_of(tag)
    require_revision(revision, tag)
    upgrade_to(unmigrated_engine, revision)

    found = unreadable_by_the_release_before(schema_facts(unmigrated_engine), schema_facts(engine))

    assert found == []


def test_the_newest_tag_is_found_by_version_not_by_text():
    assert newest_of(["v2026.11.9.2", "v2026.11.19.1", "v2026.11.19.10", "v2026.11.19.9"]) == "v2026.11.19.10"


def test_a_missing_release_tag_fails_saying_what_to_fetch():
    with pytest.raises(pytest.fail.Exception, match="git fetch --depth=1 origin tag"):
        newest_of([])


def test_a_branch_lacking_the_tags_revision_fails_saying_to_merge_main():
    with pytest.raises(pytest.fail.Exception, match="merge main"):
        require_revision("not-a-revision", "v2026.11.19.1")
