import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import MIGRATIONS_DIRECTORY, create_store_engine, migrate

pytestmark = pytest.mark.postgres


@pytest.fixture
def engine(unmigrated_database_url):
    engine = create_store_engine(unmigrated_database_url)
    yield engine
    engine.dispose()


def upgrade_to(engine, revision):
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


class TestFromOccupiedAndFreeChairsAtRevisionThirteen:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0013 holding a table with one occupied and one free chair, then taken to head."""
        upgrade_to(engine, "0013")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 7)"))
            connection.execute(
                text(
                    "INSERT INTO chairs (table_id, seat, account_id, display_name)"
                    " VALUES ('t', 1, 'account-anna', 'Anna'), ('t', 2, NULL, NULL)"
                )
            )
        migrate(engine)
        return engine

    def update(self, engine, statement):
        with engine.begin() as connection:
            connection.execute(text(statement))

    def test_fills_a_person_into_the_occupied_chair_and_leaves_the_free_one_without_a_kind(self, migrated):
        with migrated.connect() as connection:
            kinds = connection.execute(text("SELECT occupant_kind FROM chairs ORDER BY seat")).scalars().all()

        assert kinds == ["person", None]

    def test_accepts_an_agent_in_the_free_chair(self, migrated):
        self.update(migrated, "UPDATE chairs SET account_id = 'account-mozart', occupant_kind = 'agent' WHERE seat = 2")

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE chairs SET occupant_kind = 'person' WHERE seat = 2",
            "UPDATE chairs SET occupant_kind = NULL WHERE seat = 1",
            "UPDATE chairs SET occupant_kind = 'robot' WHERE seat = 1",
        ],
        ids=["a kind on a free chair", "an occupied chair without a kind", "an unknown kind"],
    )
    def test_the_checks_refuse_a_chair_whose_kind_does_not_match_its_occupant(self, migrated, statement):
        with pytest.raises(IntegrityError):
            self.update(migrated, statement)
