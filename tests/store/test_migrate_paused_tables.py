import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

ENDED_ROW = "ended_at = now(), end_reason = 'empty', empty_seconds = 60, dealer = NULL"


class TestFromADealtLiveTableAnUndealtTableAndAnEndedTableAtRevisionTwentyThree:
    @pytest.fixture
    def window(self):
        """The database time just before and just after the migration, filled by `migrated`."""
        return []

    @pytest.fixture
    def migrated(self, unmigrated_engine, window):
        """A database at 0023 holding the three tables, then taken to head."""
        upgrade_to(unmigrated_engine, "0023")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('dealt', 5, 2)"))
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('undealt', 1)"))
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                    " VALUES ('ended', 3, now(), 'empty', 60)"
                )
            )
            before = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
        migrate(unmigrated_engine)
        with unmigrated_engine.connect() as connection:
            after = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
        window.extend((before, after))
        return unmigrated_engine

    def test_the_dealt_live_table_gets_the_migration_time_and_no_opener(self, migrated, window):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT last_played_at, opener_name FROM tables WHERE id = 'dealt'")).one()

        before, after = window
        assert before <= row.last_played_at <= after
        assert row.opener_name is None

    @pytest.mark.parametrize("table_id", ["undealt", "ended"])
    def test_a_table_without_a_live_hand_keeps_both_facts_empty(self, migrated, table_id):
        with migrated.connect() as connection:
            row = connection.execute(
                text("SELECT last_played_at, opener_name FROM tables WHERE id = :id").bindparams(id=table_id)
            ).one()

        assert tuple(row) == (None, None)

    @pytest.mark.parametrize(
        "update",
        [
            "UPDATE tables SET opener_name = 'Ben' WHERE id = 'ended'",
            "UPDATE tables SET last_played_at = now() WHERE id = 'ended'",
            "UPDATE tables SET dealer = 1, last_played_at = NULL WHERE id = 'dealt'",
            "UPDATE tables SET last_played_at = now() WHERE id = 'undealt'",
            "UPDATE tables SET opener_name = '' WHERE id = 'undealt'",
            f"UPDATE tables SET {ENDED_ROW}, opener_name = 'Ben' WHERE id = 'dealt'",
        ],
        ids=[
            "an ended row with an opener name",
            "an ended row with a time",
            "a dealt row without a time",
            "a time without a dealer",
            "an empty opener name",
            "ending a dealt row that keeps its name",
        ],
    )
    def test_refuses_a_row_the_table_cannot_hold(self, migrated, update):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(update))

    def test_accepts_the_end_that_clears_both_facts(self, migrated):
        run_in_transaction(
            migrated,
            text(f"UPDATE tables SET {ENDED_ROW}, last_played_at = NULL, opener_name = NULL WHERE id = 'dealt'"),
        )

    def test_accepts_a_name_and_a_time_on_a_dealt_live_table(self, migrated):
        run_in_transaction(
            migrated, text("UPDATE tables SET opener_name = 'Ben', last_played_at = now() WHERE id = 'dealt'")
        )
