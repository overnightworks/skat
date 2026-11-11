import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from skat.store.tables import metadata
from tests.support.migrations import list_row, ramsch_list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

SECOND_SERIES_TABLE = "second"


def stored_rows(engine, columns="*"):
    statement = text(f"SELECT {columns} FROM game_list ORDER BY table_id, ordinal")  # noqa: S608 - the test's own column list
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings()]


class TestFromTablesInTheirFirstAndThirdSeriesAtRevisionTwentySeven:
    @pytest.fixture
    def at_revision(self, unmigrated_engine):
        """A database at 0027 holding a table in its first series and one in its third, each with a list whose rows
        carry the ending, Bock, push, name and seat columns.
        """
        upgrade_to(unmigrated_engine, "0027")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('first', 3)"))
            connection.execute(
                text(
                    f"INSERT INTO tables (id, version, series_length, series_deals, series_number)"  # noqa: S608 - fixed literals
                    f" VALUES ('{SECOND_SERIES_TABLE}', 9, 12, 4, 3)"
                )
            )
            connection.execute(text(list_row(table_id="'first'", seat_1_name="'Anna'", seat_3_name="'Cleo'")))
            connection.execute(text(list_row(table_id="'first'", ordinal=2, bock_factor=2, score=-96)))
            connection.execute(
                text(list_row(table_id=f"'{SECOND_SERIES_TABLE}'", ordinal=1, ending="'given-up'", ended_by_seat=2))
            )
            connection.execute(text(list_row(table_id=f"'{SECOND_SERIES_TABLE}'", ordinal=2, declarer_seat=3)))
            connection.execute(text(ramsch_list_row(table_id=f"'{SECOND_SERIES_TABLE}'", ordinal=3, pushes=2)))
        return unmigrated_engine

    @pytest.fixture
    def rows_before(self, at_revision):
        return stored_rows(at_revision)

    @pytest.fixture
    def migrated(self, at_revision, rows_before):
        migrate(at_revision)
        return at_revision

    def test_every_row_keeps_every_value_it_had_and_none_is_lost(self, migrated, rows_before):
        assert stored_rows(migrated, ", ".join(rows_before[0])) == rows_before

    def test_every_row_takes_its_tables_series_number_and_has_no_finish_time(self, migrated):
        added = stored_rows(migrated, "table_id, ordinal, series_number, finished_at")

        assert [(row["table_id"], row["ordinal"], row["series_number"], row["finished_at"]) for row in added] == [
            ("first", 1, 1, None),
            ("first", 2, 1, None),
            (SECOND_SERIES_TABLE, 1, 3, None),
            (SECOND_SERIES_TABLE, 2, 3, None),
            (SECOND_SERIES_TABLE, 3, 3, None),
        ]

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_ordinal_one_again_in_the_next_series_of_a_table(self, migrated):
        run_in_transaction(migrated, text(list_row(table_id="'first'", series_number=2)))

        rows = stored_rows(migrated, "table_id, series_number, ordinal")

        assert {"table_id": "first", "series_number": 2, "ordinal": 1} in rows

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"table_id": "'first'", "series_number": 1}, id="an-ordinal-twice-in-one-series"),
            pytest.param({"table_id": "'first'", "series_number": 0, "ordinal": 9}, id="a-series-below-the-first"),
            pytest.param({"table_id": "'first'", "series_number": "NULL", "ordinal": 9}, id="a-row-with-no-series"),
            pytest.param({"table_id": "'first'", "ordinal": 9}, id="a-row-that-leaves-the-series-out"),
        ],
    )
    def test_refuses_a_row_the_key_or_the_series_check_does_not_hold(self, migrated, changed):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(list_row(**changed)))

    def test_a_new_row_keeps_its_finish_instant_with_its_time_zone(self, migrated):
        run_in_transaction(
            migrated,
            text(list_row(table_id="'first'", ordinal=3, series_number=1, finished_at="'2026-11-11 20:15+00'")),
        )

        with migrated.connect() as connection:
            instant = connection.execute(
                text("SELECT finished_at FROM game_list WHERE ordinal = 3 AND table_id = 'first'")
            )
            assert instant.scalar_one().isoformat() == "2026-11-11T20:15:00+00:00"
