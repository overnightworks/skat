import pytest
from sqlalchemy import text

from tests.support.migrations import migrated_from

pytestmark = pytest.mark.postgres


class TestFromASeriesAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0055",
            text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('over', 8, 2, now())"),
            text("INSERT INTO series (table_id, number, length, deals) VALUES ('over', 1, 12, 12)"),
        )

    def test_a_stored_series_counts_no_saves_of_next_settings(self, migrated):
        with migrated.connect() as connection:
            revision = connection.execute(
                text("SELECT settings_revision FROM series WHERE table_id = 'over'")
            ).scalar_one()

        assert revision == 0
