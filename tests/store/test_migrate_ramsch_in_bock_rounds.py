import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import create_store_engine, migrate
from tests.support.migrations import only_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

RAMSCH_OPTIONS = "ramsch_scoring = 'points', ramsch_jungfrau = 'off', ramsch_durchmarsch = 'off'"


class TestFromATableAndARuleSetWithRamschAtRevisionForty:
    @pytest.fixture
    def migrated(self, unmigrated_database_url):
        engine = create_store_engine(unmigrated_database_url)
        upgrade_to(engine, "0041")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ramsch_occasion, ramsch_scoring, ramsch_jungfrau,"
                    " ramsch_durchmarsch) VALUES ('t', 3, 'passed-in', 'points', 'off', 'off')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO rule_sets (id, owner_account, name, ramsch_occasion, ramsch_scoring, ramsch_jungfrau,"
                    " ramsch_durchmarsch) VALUES ('1', 'a', 'x', 'passed-in', 'points', 'off', 'off')"
                )
            )
        migrate(engine)
        yield engine
        engine.dispose()

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    def test_keeps_the_stored_occasion(self, migrated, table):
        select = text(f"SELECT ramsch_occasion FROM {table}")  # noqa: S608 - only the test's fixed literals reach this text

        assert only_row(migrated, select) == ("passed-in",)

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    @pytest.mark.parametrize("occasion", ["bock-rounds", "passed-in-and-bock-rounds"])
    def test_accepts_each_new_occasion(self, migrated, table, occasion):
        run_in_transaction(
            migrated,
            text(f"UPDATE {table} SET ramsch_occasion = '{occasion}', {RAMSCH_OPTIONS}"),  # noqa: S608 - only the test's fixed literals reach this text
        )

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    def test_refuses_another_occasion(self, migrated, table):
        with pytest.raises(IntegrityError):
            run_in_transaction(
                migrated,
                text(f"UPDATE {table} SET ramsch_occasion = 'ramsch-rounds'"),  # noqa: S608 - only the test's fixed literals reach this text
            )

    def test_a_table_that_existed_has_no_ramsch_round_game_pending(self, migrated):
        select = text("SELECT ramsch_round_games FROM tables")

        assert only_row(migrated, select) == (0,)

    def test_refuses_a_negative_count_of_ramsch_round_games(self, migrated):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text("UPDATE tables SET ramsch_round_games = -1"))
