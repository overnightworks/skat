import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import EntryTraces, TableId
from tests.support.migrations import migrated_from

pytestmark = pytest.mark.postgres


class TestFromATableTheRevisionBeforeWrote:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0058",
            text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('over', 8, 2, now())"),
            text("INSERT INTO series (table_id, number, length, deals) VALUES ('over', 1, 12, 12)"),
        )

    def test_the_table_keeps_its_version_and_has_no_trace_stored(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(
                text("SELECT version, traceparent, traceparent_version, act_traceparents FROM tables")
            ).one()

        assert tuple(row) == (8, None, None, None)

    def test_the_table_reads_with_no_trace(self, migrated):

        with PostgresTableTransactions(migrated).begin() as transaction:
            record = transaction.table(TableId("over"))

        assert (record.version, record.traces) == (8, EntryTraces())
