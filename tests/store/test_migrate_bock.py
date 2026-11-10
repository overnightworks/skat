import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from skat.store.tables import metadata
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromALiveTableAndAGameAtRevisionSixteen:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0016 holding a table in play, a game list row and a saved rule set, then taken to head."""
        upgrade_to(unmigrated_engine, "0016")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text(list_row()))
            connection.execute(text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x')"))
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_the_table_plays_without_bock_and_holds_no_pending_game_and_the_old_row_has_factor_1(self, migrated):
        with migrated.connect() as connection:
            options = connection.execute(text("SELECT bock_triggers, bock_overlap, bock_rounds FROM tables")).one()
            factor = connection.execute(text("SELECT bock_factor FROM game_list")).scalar_one()

        assert (tuple(options), factor) == ((None, None, []), 1)

    def test_the_saved_rule_set_holds_no_bock_and_accepts_a_bock_option(self, migrated):
        with migrated.connect() as connection:
            before = connection.execute(text("SELECT bock_triggers, bock_overlap FROM rule_sets")).one()
        run_in_transaction(
            migrated, text("UPDATE rule_sets SET bock_triggers = ARRAY['re', 'passed-in'], bock_overlap = 'ignore'")
        )

        with migrated.connect() as connection:
            after = connection.execute(text("SELECT bock_triggers, bock_overlap FROM rule_sets")).one()

        assert (tuple(before), tuple(after)) == ((None, None), (["re", "passed-in"], "ignore"))

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    @pytest.mark.parametrize(
        "change",
        [
            pytest.param("bock_triggers = ARRAY['re']", id="triggers-without-an-overlap"),
            pytest.param("bock_overlap = 'append'", id="an-overlap-without-triggers"),
            pytest.param("bock_triggers = ARRAY[]::text[], bock_overlap = 'append'", id="no-trigger-at-all"),
            pytest.param("bock_triggers = ARRAY['double'], bock_overlap = 'append'", id="unknown-trigger"),
            pytest.param("bock_triggers = ARRAY['re'], bock_overlap = 'twice'", id="unknown-overlap"),
        ],
    )
    def test_the_checks_refuse_what_is_no_bock_option_on_a_table_or_a_rule_set(self, migrated, table, change):
        refused = text(f"UPDATE {table} SET {change}")  # noqa: S608 - only the test's fixed literals reach this text

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_the_options_the_pending_games_and_a_factor_with_a_score_beyond_a_smallint(self, migrated):
        run_in_transaction(
            migrated,
            text(
                "UPDATE tables SET bock_triggers = ARRAY['re', 'schwarz'], bock_overlap = 'multiply',"
                " bock_rounds = ARRAY[1, 3]"
            ),
        )
        run_in_transaction(migrated, text("UPDATE game_list SET bock_factor = 8, score = -61440"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT bock_rounds FROM tables")).scalar_one() == [1, 3]
            assert connection.execute(text("SELECT score FROM game_list")).scalar_one() == -61440

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'append', bock_rounds = ARRAY[0]",
                id="a-round-with-no-game-left",
            ),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'append', bock_rounds = ARRAY[4]",
                id="a-round-longer-than-three-games",
            ),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'append',"
                " bock_rounds = ARRAY[2, NULL]::smallint[]",
                id="a-round-without-a-count",
            ),
            pytest.param("UPDATE tables SET bock_rounds = ARRAY[3]", id="pending-games-at-a-table-without-bock"),
            pytest.param("UPDATE tables SET bock_rounds = NULL", id="no-pending-list"),
            pytest.param("UPDATE game_list SET bock_factor = 0", id="factor-zero"),
            pytest.param("UPDATE game_list SET bock_factor = 3", id="factor-not-a-power-of-two"),
        ],
    )
    def test_the_checks_refuse_what_is_no_pending_game_or_factor(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)
