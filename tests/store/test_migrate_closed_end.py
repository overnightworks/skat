import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromALiveTableAndAnEndedTableOfEachReasonAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        upgrade_to(unmigrated_engine, "0038")
        with unmigrated_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('dealt', 5, 2, now())")
            )
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                    " VALUES ('empty', 3, now(), 'empty', 60)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ended_at, end_reason, unplayed_days)"
                    " VALUES ('unplayed', 4, now(), 'unplayed', 90)"
                )
            )
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_nothing_changes_in_them(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, version, end_reason, empty_seconds, unplayed_days, closed_by_name"
                    " FROM tables ORDER BY id"
                )
            ).all()

        assert [tuple(row) for row in rows] == [
            ("dealt", 5, None, None, None, None),
            ("empty", 3, "empty", 60, None, None),
            ("unplayed", 4, "unplayed", None, 90, None),
        ]

    def test_accepts_a_closed_end_with_the_closers_name_that_clears_the_dealt_facts(self, migrated):
        run_in_transaction(
            migrated,
            text(
                "UPDATE tables SET ended_at = now(), end_reason = 'closed', closed_by_name = 'Anna', dealer = NULL,"
                " last_played_at = NULL WHERE id = 'dealt'"
            ),
        )

    @pytest.mark.parametrize(
        "update",
        [
            "UPDATE tables SET ended_at = now(), end_reason = 'closed', dealer = NULL, last_played_at = NULL"
            " WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'closed', closed_by_name = '', dealer = NULL,"
            " last_played_at = NULL WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'empty', empty_seconds = 60, closed_by_name = 'Anna',"
            " dealer = NULL, last_played_at = NULL WHERE id = 'dealt'",
            "UPDATE tables SET closed_by_name = 'Anna' WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'abandoned', dealer = NULL, last_played_at = NULL"
            " WHERE id = 'dealt'",
        ],
        ids=[
            "a closed end without a name",
            "a closed end with an empty name",
            "an empty end with a name",
            "a name on a live table",
            "an unknown reason",
        ],
    )
    def test_refuses_a_row_the_table_cannot_hold(self, migrated, update):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(update))
