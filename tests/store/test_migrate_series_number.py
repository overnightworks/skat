import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromASeriesTableAndASeriesLessTableAtRevisionNineteen:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0019 holding a table with a series and one without, then taken to head."""
        upgrade_to(unmigrated_engine, "0019")
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

    def test_both_tables_read_the_first_series(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(text("SELECT id, series_number FROM tables ORDER BY id")).all()

        assert [tuple(row) for row in rows] == [("plain", 1), ("series", 1)]

    def test_accepts_a_later_series_number_on_a_table_with_a_series(self, migrated):
        run_in_transaction(migrated, text("UPDATE tables SET series_number = 2 WHERE id = 'series'"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT series_number FROM tables WHERE id = 'series'")).scalar_one() == 2

    @pytest.mark.parametrize(
        ("table_id", "number"),
        [("series", 0), ("plain", 2)],
        ids=["a series numbered below one", "a later number without a series"],
    )
    def test_refuses_a_number_the_table_cannot_hold(self, migrated, table_id, number):
        with pytest.raises(IntegrityError):
            run_in_transaction(
                migrated,
                text("UPDATE tables SET series_number = :number WHERE id = :id").bindparams(number=number, id=table_id),
            )
