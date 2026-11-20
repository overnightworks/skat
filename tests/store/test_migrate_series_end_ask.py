import pytest
from sqlalchemy import text

from tests.support.migrations import migrated_from

pytestmark = pytest.mark.postgres


class TestFromAClosedTombstoneAndAnOverSeriesAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0054",
            text(
                "INSERT INTO tables (id, version, ended_at, end_reason, closed_by_name)"
                " VALUES ('closed', 3, now(), 'closed', 'Anna')"
            ),
            text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('over', 8, 2, now())"),
            text("INSERT INTO series (table_id, number, length, deals) VALUES ('over', 1, 12, 12)"),
        )

    def test_the_closed_tombstone_still_reads_with_its_closers_name(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT end_reason, closed_by_name FROM tables WHERE id = 'closed'")).one()

        assert tuple(row) == ("closed", "Anna")

    def test_an_over_series_has_asked_for_no_new_series_yet(self, migrated):
        with migrated.connect() as connection:
            asked = connection.execute(
                text("SELECT new_series_asked_at FROM series WHERE table_id = 'over'")
            ).scalar_one()

        assert asked is None
