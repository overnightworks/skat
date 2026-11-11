import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from skat.store.tables import metadata
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

SECOND_SERIES_TABLE = "second"


def ramsch_entry(**changed):
    columns = {
        "table_id": f"'{SECOND_SERIES_TABLE}'",
        "ordinal": 3,
        "seat_1_account": "'account-anna'",
        "seat_2_account": "'account-ben'",
        "seat_3_account": "'account-cleo'",
        "kind": "'ramsch'",
        "seat_1_points": 47,
        "seat_2_points": 40,
        "seat_3_points": 33,
        "seat_1_score": -47,
        "seat_2_score": 0,
        "seat_3_score": 0,
        "jungfrau": "false",
        "pushes": 2,
        **changed,
    }
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return text(f"INSERT INTO game_list ({names}) VALUES ({values})")  # noqa: S608 - only a test's fixed literals reach this text


def stored_rows(engine):
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                text(
                    "SELECT table_id, series_number, ordinal, finished_at, ending, bock_factor, pushes"
                    " FROM game_list ORDER BY table_id, ordinal"
                )
            )
        ]


class TestFromTablesInTheirFirstAndThirdSeriesAtRevisionTwentySeven:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0027 holding a table in its first series and one in its third, each with a list whose rows
        carry the ending, Bock and push columns, then taken to head.
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
            connection.execute(text(list_row(table_id="'first'")))
            connection.execute(text(list_row(table_id="'first'", ordinal=2, bock_factor=2)))
            connection.execute(
                text(list_row(table_id=f"'{SECOND_SERIES_TABLE}'", ordinal=1, ending="'given-up'", ended_by_seat=2))
            )
            connection.execute(text(list_row(table_id=f"'{SECOND_SERIES_TABLE}'", ordinal=2)))
            connection.execute(ramsch_entry())
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_every_row_takes_its_tables_series_number_and_has_no_finish_time_and_none_is_lost_or_changed(
        self, migrated
    ):
        assert stored_rows(migrated) == [
            ("first", 1, 1, None, "played-out", 1, 0),
            ("first", 1, 2, None, "played-out", 2, 0),
            (SECOND_SERIES_TABLE, 3, 1, None, "given-up", 1, 0),
            (SECOND_SERIES_TABLE, 3, 2, None, "played-out", 1, 0),
            (SECOND_SERIES_TABLE, 3, 3, None, "played-out", 1, 2),
        ]

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_ordinal_one_again_in_the_next_series_of_a_table(self, migrated):
        run_in_transaction(migrated, text(list_row(table_id="'first'", series_number=2)))

        assert ("first", 2, 1) in [row[:3] for row in stored_rows(migrated)]

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"table_id": "'first'", "series_number": 1}, id="an-ordinal-twice-in-one-series"),
            pytest.param({"table_id": "'first'", "series_number": 0, "ordinal": 9}, id="a-series-below-the-first"),
            pytest.param({"table_id": "'first'", "series_number": "NULL", "ordinal": 9}, id="a-row-with-no-series"),
        ],
    )
    def test_refuses_a_row_the_key_or_the_series_check_does_not_hold(self, migrated, changed):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(list_row(**changed)))

    def test_a_new_row_stores_an_instant_and_no_server_fills_the_series_number(self, migrated):
        run_in_transaction(
            migrated,
            text(list_row(table_id="'first'", ordinal=3, series_number=1, finished_at="'2026-11-11 20:15+00'")),
        )

        with migrated.connect() as connection:
            instant = connection.execute(
                text("SELECT finished_at FROM game_list WHERE ordinal = 3 AND table_id = 'first'")
            )
            assert instant.scalar_one().isoformat() == "2026-11-11T20:15:00+00:00"
