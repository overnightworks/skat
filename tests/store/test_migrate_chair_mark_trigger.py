import pytest
from sqlalchemy import text

from tests.support.migrations import migrated_from

pytestmark = pytest.mark.postgres

MARK_TRIGGERS_ON_CHAIRS = text(
    "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'chairs'::regclass AND NOT tgisinternal"
    " AND tgname = 'chair_mark_taken_back_names_no_settings'"
)
MARK_FUNCTIONS = text("SELECT count(*) FROM pg_proc WHERE proname = 'chair_mark_taken_back_names_no_settings'")


def test_the_trigger_that_cleared_a_marks_revision_and_its_function_are_gone(unmigrated_engine):
    migrated_from(unmigrated_engine, "0057")

    with unmigrated_engine.connect() as connection:
        triggers = connection.execute(MARK_TRIGGERS_ON_CHAIRS).scalar_one()
        functions = connection.execute(MARK_FUNCTIONS).scalar_one()

    assert (triggers, functions) == (0, 0)
