import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.tables import metadata
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

KONTRA_TABLE = (
    "INSERT INTO tables (id, version, kontra_sayer, kontra_reach, kontra_deadline)"
    " VALUES ('t', 4, 'any-opponent', 'kontra-re', 'own-card')"
)
RUNNING_KONTRA = "INSERT INTO kontra_words VALUES ('t', 1, 'forehand', 'kontra', 0)"


def no_word(position="'rearhand'", word="'kontra'"):
    return text(f"INSERT INTO kontra_no_words VALUES ('t', {position}, {word})")  # noqa: S608 - only a test's fixed literals reach this text


class TestFromATableWithARunningKontraHandAtRevisionTwentyNine:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0029 holding a table that plays Kontra with a word said in its running hand, then at head."""
        upgrade_to(unmigrated_engine, "0029")
        with unmigrated_engine.begin() as connection:
            connection.execute(text(KONTRA_TABLE))
            connection.execute(text(RUNNING_KONTRA))
        upgrade_to(unmigrated_engine, "head")
        return unmigrated_engine

    def test_the_new_table_is_empty_and_the_old_hand_keeps_its_word(self, migrated):
        with migrated.connect() as connection:
            answers = connection.execute(text("SELECT count(*) FROM kontra_no_words")).scalar_one()
            words = connection.execute(text("SELECT count(*) FROM kontra_words")).scalar_one()

        assert (answers, words) == (0, 1)

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_an_answer_of_a_seat_for_a_word_of_the_hand(self, migrated):
        run_in_transaction(migrated, no_word())
        run_in_transaction(migrated, no_word("'forehand'"))
        run_in_transaction(migrated, no_word("'rearhand'", "'re'"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM kontra_no_words")).scalar_one() == 3

    @pytest.mark.parametrize(
        "answer",
        [
            pytest.param(no_word("'dealer'"), id="unknown-position"),
            pytest.param(no_word(word="'pass'"), id="unknown-word"),
            pytest.param(
                text("INSERT INTO kontra_no_words VALUES ('nobody', 'rearhand', 'kontra')"), id="unknown-table"
            ),
        ],
    )
    def test_refuses_an_answer_that_names_no_position_word_or_table(self, migrated, answer):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, answer)

    def test_refuses_a_second_answer_of_a_seat_for_the_same_word(self, migrated):
        answer = no_word()
        run_in_transaction(migrated, answer)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, answer)
