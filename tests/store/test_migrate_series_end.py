import pytest
from sqlalchemy import text

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromASeriesTableAndASeriesLessTableAtRevisionEighteen:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0018 holding a table with a series and one without, then taken to head."""
        upgrade_to(unmigrated_engine, "0018")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('plain', 1, 2)"))
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, dealer, series_length, series_deals)"
                    " VALUES ('series', 4, 2, 12, 5)"
                )
            )
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_both_tables_read_no_proposal_and_no_early_end(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(
                text("SELECT table_id, end_proposer, end_accepter, ended_early FROM series ORDER BY table_id")
            ).all()

        assert [tuple(row) for row in rows] == [("plain", None, None, False), ("series", None, None, False)]

    def test_accepts_a_proposal_and_then_an_early_end_on_a_series(self, migrated):
        run_in_transaction(
            migrated, text("UPDATE series SET end_proposer = 1, end_accepter = 3 WHERE table_id = 'series'")
        )
        run_in_transaction(
            migrated,
            text(
                "UPDATE series SET end_proposer = NULL, end_accepter = NULL,"
                " ended_early = true WHERE table_id = 'series'"
            ),
        )

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT ended_early FROM series WHERE table_id = 'series'")).scalar_one()
