import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

INVITATION_ROW = (
    "INSERT INTO member_book (table_id, agent_account, epoch, invitation_id, invitation_expires_at, owner_account,"
    " inviter_account) VALUES ('live', 'account-mozart', 2, 'invitation', now(), 'account-anna', 'account-anna')"
)


class TestFromLiveAndEndedTablesAtRevisionTwentyFour:
    @pytest.fixture
    def stored(self, unmigrated_engine):
        """A database at 0024 holding a live table with a seated chair and an ended one, and what they hold."""
        upgrade_to(unmigrated_engine, "0024")
        with unmigrated_engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('live', 5)"))
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                    " VALUES ('ended', 3, now(), 'empty', 60)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind)"
                    " VALUES ('live', 1, 'account-anna', 'Anna', 'person'), ('live', 2, NULL, NULL, NULL)"
                )
            )
        return self.rows(unmigrated_engine), unmigrated_engine

    @staticmethod
    def rows(engine):
        with engine.connect() as connection:
            return [
                connection.execute(text(f"SELECT * FROM {name} ORDER BY 1, 2")).all()  # noqa: S608 - fixed names
                for name in ("tables", "chairs")
            ]

    @pytest.fixture
    def migrated(self, stored):
        before, engine = stored
        migrate(engine)
        return before, engine

    def test_changes_no_stored_table_and_starts_with_an_empty_book(self, migrated):
        before, engine = migrated

        assert self.rows(engine) == before
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM member_book")).scalar_one() == 0

    def test_holds_an_open_invitation_and_a_row_with_only_its_epoch(self, migrated):
        _, engine = migrated

        run_in_transaction(engine, text(INVITATION_ROW))
        run_in_transaction(
            engine, text("INSERT INTO member_book (table_id, agent_account) VALUES ('live', 'account-bach')")
        )

        with engine.connect() as connection:
            epochs = connection.execute(text("SELECT epoch FROM member_book ORDER BY agent_account")).scalars().all()
        assert epochs == [0, 2]

    @pytest.mark.parametrize(
        "statement",
        [
            "INSERT INTO member_book (table_id, agent_account, invitation_id) VALUES ('live', 'a', 'only-an-id')",
            "INSERT INTO member_book (table_id, agent_account, owner_account) VALUES ('live', 'a', 'only-an-owner')",
            "INSERT INTO member_book (table_id, agent_account, epoch) VALUES ('live', 'a', -1)",
            "INSERT INTO member_book (table_id, agent_account) VALUES ('no-such-table', 'a')",
            INVITATION_ROW.replace("'account-mozart'", "'account-anna'")
            + ", ('live', 'account-anna', 0, 'x', now(), 'o', 'i')",
        ],
        ids=["an id alone", "an owner alone", "a negative epoch", "a table that does not exist", "one row twice"],
    )
    def test_the_schema_refuses_a_row_the_book_cannot_hold(self, migrated, statement):
        _, engine = migrated

        with pytest.raises(IntegrityError):
            run_in_transaction(engine, text(statement))
