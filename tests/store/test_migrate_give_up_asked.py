import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import create_store_engine, migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromALiveTableAtRevisionFourteen:
    @pytest.fixture
    def migrated(self, unmigrated_database_url):
        """A database at 0014 holding a live table, then taken to head."""
        engine = create_store_engine(unmigrated_database_url)
        upgrade_to(engine, "0014")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 1)"))
        migrate(engine)
        yield engine
        engine.dispose()

    def test_reads_the_table_with_no_request(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT give_up_asked_by, give_up_declined_by FROM tables")).one()

        assert tuple(row) == (None, None)

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET give_up_asked_by = 'middlehand'", id="an-ask"),
            pytest.param(
                "UPDATE tables SET give_up_asked_by = 'middlehand', give_up_declined_by = 'rearhand'", id="a-no"
            ),
        ],
    )
    def test_accepts_an_ask_and_a_no_from_another_position(self, migrated, statement):
        run_in_transaction(migrated, text(statement))

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET give_up_declined_by = 'rearhand'", id="a-no-without-an-ask"),
            pytest.param("UPDATE tables SET give_up_asked_by = 'dealer'", id="an-ask-that-is-no-position"),
            pytest.param(
                "UPDATE tables SET give_up_asked_by = 'middlehand', give_up_declined_by = 'skat'",
                id="a-no-that-is-no-position",
            ),
            pytest.param(
                "UPDATE tables SET give_up_asked_by = 'middlehand', give_up_declined_by = 'middlehand'",
                id="a-no-from-the-asker",
            ),
        ],
    )
    def test_refuses_what_is_no_request(self, migrated, statement):
        update = text(statement)
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, update)
