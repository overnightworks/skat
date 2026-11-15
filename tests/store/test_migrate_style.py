import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.support.migrations import migrated_from, only_row, run_in_transaction

pytestmark = pytest.mark.postgres


class TestFromATableAtRevisionFortyFive:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0045 holding two tables, then taken to head."""
        return migrated_from(
            unmigrated_engine, "0045", text("INSERT INTO tables (id, version) VALUES ('first', 1), ('second', 2)")
        )

    def test_every_table_that_exists_reads_klassik(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(text("SELECT id, style FROM tables ORDER BY id")).all()

        assert [tuple(row) for row in rows] == [("first", "klassik"), ("second", "klassik")]

    def test_accepts_the_other_style(self, migrated):
        run_in_transaction(migrated, text("UPDATE tables SET style = 'strandbar' WHERE id = 'first'"))

        assert only_row(migrated, text("SELECT style FROM tables WHERE id = 'first'")) == ("strandbar",)

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET style = 'pokerkeller'", id="an-unknown-style"),
            pytest.param("UPDATE tables SET style = NULL", id="no-style"),
        ],
    )
    def test_the_checks_refuse_what_is_no_style(self, migrated, statement):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(statement))
