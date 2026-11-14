import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from skat.table.service import TableService
from tests.support.migrations import migrated_from, run_in_transaction

pytestmark = pytest.mark.postgres


class TestFromTablesStoredAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0039",
            text("INSERT INTO tables (id, version) VALUES ('undealt', 1)"),
            text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('dealt', 5, 2, now())"),
            text(
                "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                " VALUES ('ended', 3, now(), 'empty', 60)"
            ),
        )

    def test_every_table_is_open_and_keeps_its_other_columns(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(text("SELECT id, version, end_reason, visibility FROM tables ORDER BY id")).all()

        assert [tuple(row) for row in rows] == [
            ("dealt", 5, None, "open"),
            ("ended", 3, "empty", "open"),
            ("undealt", 1, None, "open"),
        ]

    def test_the_live_tables_are_listed_to_the_lobby_and_the_ended_one_is_not(self, migrated):
        listed = TableService(PostgresTableTransactions(migrated)).open_table_ids()

        assert listed == (TableId("dealt"), TableId("undealt"))

    def test_a_row_written_without_a_visibility_is_open(self, migrated):
        run_in_transaction(migrated, text("INSERT INTO tables (id, version) VALUES ('later', 1)"))

        with migrated.connect() as connection:
            visibility = connection.execute(text("SELECT visibility FROM tables WHERE id = 'later'")).scalar_one()

        assert visibility == "open"

    def test_a_visibility_other_than_open_or_private_is_refused(self, migrated):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text("UPDATE tables SET visibility = 'secret' WHERE id = 'undealt'"))
