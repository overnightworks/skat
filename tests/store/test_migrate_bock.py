import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import create_store_engine, migrate
from skat.store.tables import metadata
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


@pytest.fixture
def engine(unmigrated_database_url):
    engine = create_store_engine(unmigrated_database_url)
    yield engine
    engine.dispose()


class TestFromALiveTableAndAGameAtRevisionFourteen:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0014 holding a table in play and a game list row, then taken to head."""
        upgrade_to(engine, "0014")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text(list_row()))
        migrate(engine)
        return engine

    def test_the_table_plays_without_bock_and_holds_no_pending_game_and_the_old_row_has_factor_1(self, migrated):
        with migrated.connect() as connection:
            options = connection.execute(text("SELECT bock_triggers, bock_overlap, bock_rounds FROM tables")).one()
            factor = connection.execute(text("SELECT bock_factor FROM game_list")).scalar_one()

        assert (tuple(options), factor) == ((None, None, []), 1)

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
            pytest.param("UPDATE tables SET bock_triggers = ARRAY['re']", id="triggers-without-an-overlap"),
            pytest.param("UPDATE tables SET bock_overlap = 'append'", id="an-overlap-without-triggers"),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY[]::text[], bock_overlap = 'append'", id="no-trigger-at-all"
            ),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['double'], bock_overlap = 'append'", id="unknown-trigger"
            ),
            pytest.param("UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'twice'", id="unknown-overlap"),
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
    def test_the_checks_refuse_what_is_no_bock_option_or_pending_game_or_factor(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)
