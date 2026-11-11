import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from skat.store.tables import metadata
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

RAMSCH_OPTIONS = (
    "ramsch_occasion = 'passed-in', ramsch_scoring = 'points', ramsch_jungfrau = 'off', ramsch_durchmarsch = 'off'"
)


def ramsch_entry(**changed):
    columns = {
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
        **changed,
    }
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return text(f"INSERT INTO game_list ({names}) VALUES ({values})")  # noqa: S608 - only a test's fixed literals reach this text


def step(**changed):
    columns = {"table_id": "'t'", "ordinal": 1, "position": "'forehand'", "action": "'take'", **changed}
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return text(f"INSERT INTO pushing_steps ({names}) VALUES ({values})")  # noqa: S608 - only a test's fixed literals reach this text


class TestFromARamschTableAndItsListAtRevisionTwentySix:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0026 holding a table that plays Ramsch, its list and a saved set, then taken to head."""
        upgrade_to(unmigrated_engine, "0026")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 3)"))
            connection.execute(text(f"UPDATE tables SET {RAMSCH_OPTIONS}"))  # noqa: S608 - a fixed literal
            connection.execute(text(list_row()))
            connection.execute(ramsch_entry())
            connection.execute(text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x')"))
        migrate(unmigrated_engine)
        return unmigrated_engine

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    def test_every_old_table_and_set_reads_no_pushing_rule(self, migrated, table):
        select = text(f"SELECT ramsch_pushing FROM {table}")  # noqa: S608 - only the test's fixed literals reach this text
        with migrated.connect() as connection:
            assert connection.execute(select).scalar_one() is None

    def test_every_old_list_row_reads_no_push(self, migrated):
        with migrated.connect() as connection:
            pushes = connection.execute(text("SELECT pushes FROM game_list ORDER BY ordinal")).scalars().all()

        assert pushes == [0, 0]

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_a_pushing_rule_on_a_table_that_plays_ramsch_and_a_ramsch_row_with_its_pushes(self, migrated):
        run_in_transaction(migrated, text("UPDATE tables SET ramsch_pushing = 'jacks-may-go'"))
        run_in_transaction(migrated, text("UPDATE game_list SET pushes = 3 WHERE kind = 'ramsch'"))

        with migrated.connect() as connection:
            row = connection.execute(
                text("SELECT t.ramsch_pushing, g.pushes FROM tables t, game_list g WHERE g.kind = 'ramsch'")
            ).one()

        assert tuple(row) == ("jacks-may-go", 3)

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET ramsch_pushing = 'always'", id="a-rule-outside-the-three"),
            pytest.param("UPDATE rule_sets SET ramsch_pushing = 'jacks-stay'", id="a-set-with-pushing-and-no-ramsch"),
            pytest.param("UPDATE game_list SET pushes = 4 WHERE kind = 'ramsch'", id="four-pushes"),
            pytest.param("UPDATE game_list SET pushes = -1 WHERE kind = 'ramsch'", id="negative-pushes"),
            pytest.param("UPDATE game_list SET pushes = 1 WHERE kind = 'declared'", id="a-declared-game-with-a-push"),
        ],
    )
    def test_refuses_a_pushing_fact_that_is_none(self, migrated, statement):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(statement))

    def test_accepts_the_steps_of_a_stage_and_refuses_a_position_outside_the_vocabulary(self, migrated):
        run_in_transaction(migrated, step())

        outside_the_vocabulary = step(ordinal=2, position="'dealer'", action="'push'")

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, outside_the_vocabulary)

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"action": "'declare'"}, id="an-action-outside-the-three"),
            pytest.param({"ordinal": 7}, id="a-seventh-step"),
            pytest.param({"first_suit": "'hearts'", "first_rank": "'ace'"}, id="cards-on-a-take"),
            pytest.param({"action": "'put-back'"}, id="a-put-back-without-cards"),
            pytest.param(
                {
                    "action": "'put-back'",
                    "first_suit": "'hearts'",
                    "first_rank": "'ace'",
                    "second_suit": "'hearts'",
                    "second_rank": "'ace'",
                },
                id="a-put-back-of-one-card-twice",
            ),
        ],
    )
    def test_refuses_a_step_that_is_none(self, migrated, changed):
        refused_step = step(**changed)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused_step)
