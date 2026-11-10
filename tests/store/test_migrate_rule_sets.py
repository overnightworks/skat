import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromALiveTableAtRevisionFourteen:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0014 holding a table that plays Kontra, then taken to head."""
        upgrade_to(unmigrated_engine, "0014")
        with unmigrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, show_running_points, kontra_sayer, kontra_reach, kontra_deadline)"
                    " VALUES ('t', 3, true, 'bidders-only', 'up-to-hirsch', 'own-card')"
                )
            )
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_the_table_reads_its_options_as_before_and_no_set_exists(self, migrated):
        with migrated.connect() as connection:
            options = connection.execute(
                text("SELECT show_running_points, kontra_sayer, kontra_reach, kontra_deadline FROM tables")
            ).one()
            sets = connection.execute(text("SELECT count(*) FROM rule_sets")).scalar_one()

        assert (tuple(options), sets) == ((True, "bidders-only", "up-to-hirsch", "own-card"), 0)

    def test_accepts_a_set_with_the_official_rules_and_one_name_for_each_owner(self, migrated):
        run_in_transaction(migrated, text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x')"))
        run_in_transaction(migrated, text("INSERT INTO rule_sets (id, owner_account, name) VALUES ('2', 'b', 'x')"))

        with migrated.connect() as connection:
            assert (
                connection.execute(text("SELECT show_running_points FROM rule_sets WHERE id = '1'")).scalar_one()
                is False
            )

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', '')", id="empty-name"),
            pytest.param(
                "INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', repeat('x', 41))",
                id="name-of-41-characters",
            ),
            pytest.param("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', NULL)", id="no-name"),
            pytest.param("INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', NULL, 'x')", id="no-owner"),
            pytest.param(
                "INSERT INTO rule_sets (id, owner_account, name, show_running_points) VALUES ('1', 'a', 'x', NULL)",
                id="no-switch",
            ),
            pytest.param(
                "INSERT INTO rule_sets (id, owner_account, name, kontra_sayer) VALUES ('1', 'a', 'x', 'any-opponent')",
                id="partial-kontra",
            ),
            pytest.param(
                "INSERT INTO rule_sets (id, owner_account, name, kontra_sayer, kontra_reach, kontra_deadline)"
                " VALUES ('1', 'a', 'x', 'anyone', 'kontra-re', 'own-card')",
                id="unknown-sayer",
            ),
            pytest.param(
                "INSERT INTO rule_sets (id, owner_account, name) VALUES ('1', 'a', 'x'), ('2', 'a', 'x')",
                id="one-name-twice-for-one-owner",
            ),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_rule_set(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, refused)
