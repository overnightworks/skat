import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.support.migrations import migrated_from, run_in_transaction

pytestmark = pytest.mark.postgres


class TestFromALiveDealtTableAnUndealtTableAndAnEmptyEndAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0034",
            text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('dealt', 5, 2, now())"),
            text("INSERT INTO tables (id, version) VALUES ('undealt', 1)"),
            text(
                "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                " VALUES ('ended', 3, now(), 'empty', 60)"
            ),
        )

    def test_nothing_changes_in_them(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(
                text("SELECT id, version, end_reason, empty_seconds, unplayed_days FROM tables ORDER BY id")
            ).all()

        assert [tuple(row) for row in rows] == [
            ("dealt", 5, None, None, None),
            ("ended", 3, "empty", 60, None),
            ("undealt", 1, None, None, None),
        ]

    def test_accepts_an_unplayed_end_with_its_days_that_clears_the_dealt_facts(self, migrated):
        run_in_transaction(
            migrated,
            text(
                "UPDATE tables SET ended_at = now(), end_reason = 'unplayed', unplayed_days = 90, dealer = NULL,"
                " last_played_at = NULL WHERE id = 'dealt'"
            ),
        )

    @pytest.mark.parametrize(
        "update",
        [
            "UPDATE tables SET ended_at = now(), end_reason = 'unplayed', dealer = NULL, last_played_at = NULL"
            " WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'empty', empty_seconds = 60, unplayed_days = 90,"
            " dealer = NULL, last_played_at = NULL WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'unplayed', unplayed_days = 0, dealer = NULL,"
            " last_played_at = NULL WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'unplayed', unplayed_days = 90, empty_seconds = 60,"
            " dealer = NULL, last_played_at = NULL WHERE id = 'dealt'",
            "UPDATE tables SET unplayed_days = 90 WHERE id = 'dealt'",
            "UPDATE tables SET ended_at = now(), end_reason = 'closed', dealer = NULL, last_played_at = NULL"
            " WHERE id = 'dealt'",
        ],
        ids=[
            "an unplayed end without days",
            "an empty end with days",
            "days of zero",
            "an unplayed end with seconds",
            "days on a live table",
            "an unknown reason",
        ],
    )
    def test_refuses_a_row_the_table_cannot_hold(self, migrated, update):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(update))
