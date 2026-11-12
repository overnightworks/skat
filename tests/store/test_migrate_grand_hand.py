import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.engine.schieberamsch import GrandHandRule
from skat.store.migrate import migrate
from skat.store.tables import metadata
from tests.support.migrations import run_in_transaction, upgrade_to
from tests.support.rule_set_rows import sets_of

pytestmark = pytest.mark.postgres

RAMSCH_OPTIONS = (
    "ramsch_occasion = 'passed-in', ramsch_scoring = 'points', ramsch_jungfrau = 'off', ramsch_durchmarsch = 'off'"
)


def step(**changed):
    columns = {"table_id": "'t'", "ordinal": 1, "position": "'forehand'", "action": "'grand-hand'", **changed}
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return text(f"INSERT INTO pushing_steps ({names}) VALUES ({values})")  # noqa: S608 - only a test's fixed literals reach this text


class TestFromATableWithPushingAtRevisionThirtyTwo:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0032 holding a table and a rule set that play a Ramsch with pushing, then taken to head."""
        upgrade_to(unmigrated_engine, "0032")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 3)"))
            connection.execute(text(f"UPDATE tables SET {RAMSCH_OPTIONS}, ramsch_pushing = 'jacks-stay'"))  # noqa: S608 - a fixed literal
            connection.execute(text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x')"))
            connection.execute(text(f"UPDATE rule_sets SET {RAMSCH_OPTIONS}, ramsch_pushing = 'jacks-stay'"))  # noqa: S608 - a fixed literal
            connection.execute(
                text(
                    "INSERT INTO pushing_steps (table_id, ordinal, position, action)"
                    " VALUES ('t', 1, 'forehand', 'push')"
                )
            )
        migrate(unmigrated_engine)
        return unmigrated_engine

    @pytest.mark.parametrize("table", ["tables", "rule_sets"])
    def test_every_old_table_and_set_reads_no_grand_hand_choice(self, migrated, table):
        select = text(f"SELECT ramsch_grand_hand FROM {table}")  # noqa: S608 - only the test's fixed literals reach this text
        with migrated.connect() as connection:
            assert connection.execute(select).scalar_one() is None

    def test_an_old_set_reads_the_grand_hand_off(self, migrated):
        (rule_set,) = sets_of(migrated, "a")

        assert rule_set.options.ramsch.grand_hand is GrandHandRule.OFF

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    @pytest.mark.parametrize("value", ["allowed", "off"])
    def test_accepts_a_grand_hand_choice_on_a_table_with_pushing(self, migrated, value):
        run_in_transaction(migrated, text(f"UPDATE tables SET ramsch_grand_hand = '{value}'"))  # noqa: S608 - a fixed literal

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET ramsch_grand_hand = 'always'", id="a-choice-outside-the-two"),
            pytest.param(
                "UPDATE rule_sets SET ramsch_pushing = NULL, ramsch_grand_hand = 'allowed'",
                id="a-set-with-a-choice-and-no-pushing",
            ),
        ],
    )
    def test_refuses_a_grand_hand_choice_that_is_none(self, migrated, statement):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(statement))

    def test_keeps_the_stored_steps_and_accepts_the_new_one_after_them(self, migrated):
        run_in_transaction(migrated, step(ordinal=2, position="'middlehand'"))

        with migrated.connect() as connection:
            actions = connection.execute(text("SELECT action FROM pushing_steps ORDER BY ordinal")).scalars().all()

        assert actions == ["push", "grand-hand"]

    def test_refuses_a_grand_hand_step_with_cards(self, migrated):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, step(ordinal=2, first_suit="'hearts'", first_rank="'ace'"))
