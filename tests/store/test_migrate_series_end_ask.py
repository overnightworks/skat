import pytest
from sqlalchemy import text

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromAClosedTombstoneAndAnOverSeriesAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        upgrade_to(unmigrated_engine, "0054")
        with unmigrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ended_at, end_reason, closed_by_name)"
                    " VALUES ('closed', 3, now(), 'closed', 'Anna')"
                )
            )
            connection.execute(
                text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('over', 8, 2, now())")
            )
            connection.execute(text("INSERT INTO series (table_id, number, length, deals) VALUES ('over', 1, 12, 12)"))
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_the_closed_tombstone_still_reads_with_its_closers_name(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT end_reason, closed_by_name FROM tables WHERE id = 'closed'")).one()

        assert tuple(row) == ("closed", "Anna")

    def test_an_over_series_has_asked_for_no_new_series_yet(self, migrated):
        with migrated.connect() as connection:
            asked = connection.execute(
                text("SELECT new_series_asked_at FROM series WHERE table_id = 'over'")
            ).scalar_one()

        assert asked is None

    def test_a_table_may_end_as_stopped_with_no_further_fact(self, migrated):
        run_in_transaction(
            migrated,
            text(
                "UPDATE tables SET ended_at = now(), end_reason = 'stopped', dealer = NULL, last_played_at = NULL"
                " WHERE id = 'over'"
            ),
        )

        with migrated.connect() as connection:
            reason = connection.execute(text("SELECT end_reason FROM tables WHERE id = 'over'")).scalar_one()
        assert reason == "stopped"

    def test_a_deal_of_the_release_before_clears_the_instant_it_never_knew(self, migrated):
        run_in_transaction(migrated, text("UPDATE series SET new_series_asked_at = now() WHERE table_id = 'over'"))

        run_in_transaction(migrated, text("UPDATE series SET deals = 1 WHERE table_id = 'over'"))

        with migrated.connect() as connection:
            asked = connection.execute(
                text("SELECT new_series_asked_at FROM series WHERE table_id = 'over'")
            ).scalar_one()
        assert asked is None

    def test_a_write_that_keeps_the_deals_keeps_the_instant(self, migrated):
        run_in_transaction(migrated, text("UPDATE series SET new_series_asked_at = now() WHERE table_id = 'over'"))

        run_in_transaction(migrated, text("UPDATE series SET ended_early = false WHERE table_id = 'over'"))

        with migrated.connect() as connection:
            asked = connection.execute(
                text("SELECT new_series_asked_at FROM series WHERE table_id = 'over'")
            ).scalar_one()
        assert asked is not None

    def test_a_write_that_sets_the_instant_with_the_deals_keeps_it(self, migrated):
        run_in_transaction(migrated, text("UPDATE series SET deals = 11 WHERE table_id = 'over'"))

        run_in_transaction(
            migrated, text("UPDATE series SET deals = 12, new_series_asked_at = now() WHERE table_id = 'over'")
        )

        with migrated.connect() as connection:
            asked = connection.execute(
                text("SELECT new_series_asked_at FROM series WHERE table_id = 'over'")
            ).scalar_one()
        assert asked is not None
