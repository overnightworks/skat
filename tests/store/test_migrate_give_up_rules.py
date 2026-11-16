import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from skat.store.tables import metadata
from skat.table.records import GiveUpOptions
from tests.support.migrations import migrated_from, only_row
from tests.support.rule_set_rows import sets_of

pytestmark = pytest.mark.postgres


class TestFromASeriesAndASetAtRevisionFortyNine:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0049 holding a table with its first series and a rule set, then taken to head."""
        return migrated_from(
            unmigrated_engine,
            "0049",
            text("INSERT INTO tables (id, version) VALUES ('t', 1)"),
            text("INSERT INTO series (table_id, number) VALUES ('t', 1)"),
            text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x')"),
        )

    @pytest.mark.parametrize("table", ["series", "rule_sets"])
    def test_every_old_series_and_set_plays_both_special_rules_off(self, migrated, table):
        select = text(f"SELECT give_up_partner_agrees, give_up_any_time FROM {table}")  # noqa: S608 - only the test's fixed literals reach this text

        assert only_row(migrated, select) == (False, False)

    def test_an_old_set_reads_the_official_give_up(self, migrated):
        (rule_set,) = sets_of(migrated, "a")

        assert rule_set.options.give_up == GiveUpOptions()

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []
