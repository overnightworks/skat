import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromOccupiedAndFreeChairsAtRevisionSeventeen:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0017 holding a table with one occupied and one free chair, then taken to head."""
        upgrade_to(unmigrated_engine, "0017")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 7)"))
            connection.execute(
                text(
                    "INSERT INTO chairs (table_id, seat, account_id, display_name)"
                    " VALUES ('t', 1, 'account-anna', 'Anna'), ('t', 2, NULL, NULL)"
                )
            )
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_fills_a_person_into_the_occupied_chair_and_leaves_the_free_one_without_a_kind(self, migrated):
        with migrated.connect() as connection:
            kinds = connection.execute(text("SELECT occupant_kind FROM chairs ORDER BY seat")).scalars().all()

        assert kinds == ["person", None]

    def test_accepts_an_agent_in_the_free_chair(self, migrated):
        run_in_transaction(
            migrated, text("UPDATE chairs SET account_id = 'account-mozart', occupant_kind = 'agent' WHERE seat = 2")
        )

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
            run_in_transaction(migrated, text(statement))
