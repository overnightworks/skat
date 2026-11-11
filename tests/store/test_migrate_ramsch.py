import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from skat.store.tables import metadata
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

RAMSCH_COLUMNS = {
    "table_id": "'t'",
    "ordinal": 2,
    "seat_1_account": "'account-anna'",
    "seat_2_account": "'account-ben'",
    "seat_3_account": "'account-cleo'",
    "kind": "'ramsch'",
    "seat_1_points": 47,
    "seat_2_points": 40,
    "seat_3_points": 33,
    "seat_1_score": -47,
    "seat_2_score": 0,
    "seat_3_score": 0,
    "jungfrau": "false",
}


def ramsch_row(**changed):
    columns = {**RAMSCH_COLUMNS, **changed}
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return text(f"INSERT INTO game_list ({names}) VALUES ({values})")  # noqa: S608 - only a test's fixed literals reach this text


class TestFromALiveTableAndAGameAtRevisionTwenty:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0020 holding a table in play, a game list row and a saved rule set, then taken to head."""
        upgrade_to(unmigrated_engine, "0020")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text(list_row()))
            connection.execute(text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x')"))
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_the_old_row_reads_declared_with_its_values_and_no_ramsch_column(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT kind, declarer_seat, game, score, seat_1_points, durchmarsch_seat, jungfrau FROM game_list"
                )
            ).one()

        assert tuple(row) == ("declared", 1, "kreuz", 48, None, None, None)

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    def test_the_old_table_and_rule_set_play_without_ramsch(self, migrated, table):
        columns = "ramsch_occasion, ramsch_scoring, ramsch_jungfrau, ramsch_durchmarsch"
        select = text(f"SELECT {columns} FROM {table}")  # noqa: S608 - only the test's fixed literals reach this text
        with migrated.connect() as connection:
            options = connection.execute(select).one()

        assert tuple(options) == (None, None, None, None)

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_a_ramsch_row_with_its_seats_and_a_score_beyond_a_smallint(self, migrated):
        run_in_transaction(migrated, ramsch_row(seat_1_score=-61440, durchmarsch_seat=2))

        with migrated.connect() as connection:
            row = connection.execute(
                text("SELECT kind, game, seat_1_score, durchmarsch_seat FROM game_list WHERE ordinal = 2")
            ).one()

        assert tuple(row) == ("ramsch", None, -61440, 2)

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"game": "'kreuz'"}, id="a-ramsch-with-a-game"),
            pytest.param({"declarer_seat": 1}, id="a-ramsch-with-a-declarer"),
            pytest.param({"bid": 18}, id="a-ramsch-with-a-bid"),
            pytest.param({"kontra_word": "'kontra'"}, id="a-ramsch-with-a-word"),
            pytest.param({"matadors_mit": "true", "matadors_count": 2}, id="a-ramsch-with-matadors"),
            pytest.param({"seat_3_score": "NULL"}, id="a-ramsch-without-a-score"),
            pytest.param({"seat_2_points": "NULL"}, id="a-ramsch-without-points"),
            pytest.param({"jungfrau": "NULL"}, id="a-ramsch-without-the-jungfrau-fact"),
            pytest.param({"seat_1_points": 121}, id="points-beyond-the-card-points"),
            pytest.param({"seat_1_points": -1}, id="negative-points"),
            pytest.param({"durchmarsch_seat": 4}, id="a-durchmarsch-by-no-seat"),
            pytest.param({"kind": "'push'"}, id="an-unknown-kind"),
        ],
    )
    def test_refuses_a_ramsch_row_that_is_no_ramsch(self, migrated, changed):
        refused = ramsch_row(**changed)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param("seat_1_points = 40", id="a-declared-row-with-points"),
            pytest.param("seat_2_score = 0", id="a-declared-row-with-a-score"),
            pytest.param("durchmarsch_seat = 1", id="a-declared-row-with-a-durchmarsch"),
            pytest.param("jungfrau = false", id="a-declared-row-with-the-jungfrau-fact"),
            pytest.param("game = NULL", id="a-declared-row-without-a-game"),
            pytest.param("matadors_mit = NULL, matadors_count = NULL", id="a-suit-game-without-matadors"),
            pytest.param("kind = 'ramsch'", id="a-declared-row-called-a-ramsch"),
        ],
    )
    def test_refuses_a_declared_row_that_is_no_declared_game(self, migrated, change):
        refused = text(f"UPDATE game_list SET {change}")  # noqa: S608 - only the test's fixed literals reach this text

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    @pytest.mark.parametrize(
        "change",
        [
            pytest.param("ramsch_occasion = 'passed-in'", id="an-occasion-alone"),
            pytest.param(
                "ramsch_occasion = 'passed-in', ramsch_scoring = 'points', ramsch_jungfrau = 'off'",
                id="three-of-four",
            ),
            pytest.param(
                "ramsch_occasion = 'ramsch-rounds', ramsch_scoring = 'points', ramsch_jungfrau = 'off',"
                " ramsch_durchmarsch = 'off'",
                id="unknown-occasion",
            ),
            pytest.param(
                "ramsch_occasion = 'passed-in', ramsch_scoring = 'tens', ramsch_jungfrau = 'off',"
                " ramsch_durchmarsch = 'off'",
                id="unknown-scoring",
            ),
            pytest.param(
                "ramsch_occasion = 'passed-in', ramsch_scoring = 'points', ramsch_jungfrau = 'twice',"
                " ramsch_durchmarsch = 'off'",
                id="unknown-jungfrau",
            ),
            pytest.param(
                "ramsch_occasion = 'passed-in', ramsch_scoring = 'points', ramsch_jungfrau = 'off',"
                " ramsch_durchmarsch = 'wins-240'",
                id="unknown-durchmarsch",
            ),
        ],
    )
    def test_the_checks_refuse_what_is_no_ramsch_option_on_a_table_or_a_rule_set(self, migrated, table, change):
        refused = text(f"UPDATE {table} SET {change}")  # noqa: S608 - only the test's fixed literals reach this text

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    def test_accepts_the_four_ramsch_options_together(self, migrated, table):
        options = (
            "ramsch_occasion = 'passed-in', ramsch_scoring = 'skat-to-loser',"
            " ramsch_jungfrau = 'off', ramsch_durchmarsch = 'wins-120-flat'"
        )
        update = text(f"UPDATE {table} SET {options}")  # noqa: S608 - only the test's fixed literals reach this text
        run_in_transaction(migrated, update)

        with migrated.connect() as connection:
            stored = connection.execute(text(f"SELECT ramsch_scoring FROM {table}")).scalar_one()  # noqa: S608 - fixed literal

        assert stored == "skat-to-loser"
