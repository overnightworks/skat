import pytest

from skat.store.migrate import declares_contraction
from tests.support.migrations import FixtureRevision, revisions_from, upgrade_to, write_revisions
from tests.support.schema_contractions import contractions, schema_facts

pytestmark = pytest.mark.postgres

# The first revision written for a pod that may run beside an older release; the earlier ones contracted freely.
FIRST_CHECKED_REVISION = "0049"

SCRATCH = (
    "CREATE TABLE other (id integer PRIMARY KEY)",
    "CREATE TABLE scratch (id integer PRIMARY KEY, name text, kept text NOT NULL DEFAULT 'x', other_id integer)",
)
CONTRACTING_STEPS = {
    "drops a table": ("DROP TABLE other", "table other is dropped"),
    "drops a column": ("ALTER TABLE scratch DROP COLUMN name", "column name is dropped"),
    "changes a column type": ("ALTER TABLE scratch ALTER COLUMN name TYPE varchar(5)", "changes its type"),
    "makes a column NOT NULL": ("ALTER TABLE scratch ALTER COLUMN name SET NOT NULL", "becomes NOT NULL"),
    "adds a NOT NULL column without a default": (
        "ALTER TABLE scratch ADD COLUMN extra text NOT NULL",
        "NOT NULL without a default",
    ),
    "drops a server default": ("ALTER TABLE scratch ALTER COLUMN kept DROP DEFAULT", "server default"),
    "changes a server default": ("ALTER TABLE scratch ALTER COLUMN kept SET DEFAULT 'y'", "server default"),
    "adds a unique constraint": ("ALTER TABLE scratch ADD UNIQUE (name)", "unique constraint or index"),
    "adds a unique index": ("CREATE UNIQUE INDEX scratch_name ON scratch (name)", "unique constraint or index"),
    "adds a check constraint": ("ALTER TABLE scratch ADD CHECK (length(name) > 1)", "check"),
    "adds a foreign key": ("ALTER TABLE scratch ADD FOREIGN KEY (other_id) REFERENCES other (id)", "foreign key"),
    "changes the primary key": (
        "ALTER TABLE scratch DROP CONSTRAINT scratch_pkey, ADD PRIMARY KEY (kept)",
        "primary key",
    ),
}
EXPANDING_STEPS = {
    "adds a table": "CREATE TABLE added (id integer PRIMARY KEY)",
    "adds a nullable column": "ALTER TABLE scratch ADD COLUMN extra text",
    "adds a NOT NULL column with a default": "ALTER TABLE scratch ADD COLUMN extra text NOT NULL DEFAULT 'x'",
    "lets a column hold NULL": "ALTER TABLE scratch ALTER COLUMN kept DROP NOT NULL",
    "gives a column a default": "ALTER TABLE scratch ALTER COLUMN name SET DEFAULT 'y'",
    "adds a plain index": "CREATE INDEX scratch_name ON scratch (name)",
}


def contractions_of_a_step_after(engine, directory, setup, step):
    """What `step` takes away from a schema that `setup` built, both applied as revisions through the real `env.py`."""
    write_revisions(directory, FixtureRevision("setup", setup), FixtureRevision("step", (step,)))
    upgrade_to(engine, "setup", extra_versions=directory)
    before = schema_facts(engine)
    upgrade_to(engine, "step", extra_versions=directory)
    return contractions(before, schema_facts(engine))


@pytest.mark.parametrize(("step", "named"), CONTRACTING_STEPS.values(), ids=CONTRACTING_STEPS.keys())
def test_the_check_catches_a_revision_that(engine, tmp_path, step, named):
    found = contractions_of_a_step_after(engine, tmp_path, SCRATCH, step)

    assert [each for each in found if named in each]


@pytest.mark.parametrize("step", EXPANDING_STEPS.values(), ids=EXPANDING_STEPS.keys())
def test_the_check_lets_a_revision_through_that(engine, tmp_path, step):
    assert contractions_of_a_step_after(engine, tmp_path, SCRATCH, step) == []


def test_every_revision_from_the_first_checked_one_on_only_expands_unless_it_declares_a_contraction(unmigrated_engine):
    steps = revisions_from(FIRST_CHECKED_REVISION)
    upgrade_to(unmigrated_engine, steps[0].down_revision)
    found = []

    for step in steps:
        before = schema_facts(unmigrated_engine)
        upgrade_to(unmigrated_engine, step.revision)
        if not declares_contraction(step):
            found.extend(f"{step.revision}: {each}" for each in contractions(before, schema_facts(unmigrated_engine)))

    assert found == []
