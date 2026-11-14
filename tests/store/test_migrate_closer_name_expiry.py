import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.support.migrations import migrated_from, run_in_transaction

pytestmark = pytest.mark.postgres


class TestFromAClosedTableAndAnEmptiedOneAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0043",
            text(
                "INSERT INTO tables (id, version, ended_at, end_reason, closed_by_name)"
                " VALUES ('closed', 3, now(), 'closed', 'Anna')"
            ),
            text(
                "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                " VALUES ('empty', 4, now(), 'empty', 60)"
            ),
        )

    def test_nothing_changes_in_them(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(text("SELECT id, version, closed_by_name FROM tables ORDER BY id")).all()

        assert [tuple(row) for row in rows] == [("closed", 3, "Anna"), ("empty", 4, None)]

    def test_accepts_a_closed_end_whose_name_was_cleared(self, migrated):
        run_in_transaction(migrated, text("UPDATE tables SET closed_by_name = NULL WHERE id = 'closed'"))

    @pytest.mark.parametrize(
        "update",
        [
            "UPDATE tables SET closed_by_name = 'Anna' WHERE id = 'empty'",
            "UPDATE tables SET closed_by_name = '' WHERE id = 'closed'",
        ],
        ids=["a name on an empty end", "an empty name"],
    )
    def test_refuses_a_row_the_table_cannot_hold(self, migrated, update):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(update))
