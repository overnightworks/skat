import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from tests.support.migrations import upgrade_to

pytestmark = pytest.mark.postgres

TABLE = "0123456789abcdef0123456789abcdef"
STORED_INVITATION = (
    "INSERT INTO member_book (table_id, agent_account, invitation_id, invitation_expires_at, owner_account,"
    " inviter_account) VALUES (:table, 'account-mozart', 'invitation', now(), 'account-anna', 'account-anna')"
)


@pytest.fixture
def before_the_upgrade(unmigrated_engine):
    """A database at 0037 holding a table with an invitation to an agent."""
    upgrade_to(unmigrated_engine, "0037")
    with unmigrated_engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES (:table, 1)"), {"table": TABLE})
        connection.execute(text(STORED_INVITATION), {"table": TABLE})
    return unmigrated_engine


def test_an_invitation_stored_before_the_upgrade_reads_as_one_that_ran_out_when_it_has_ended(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")

    with PostgresTableTransactions(before_the_upgrade).begin() as transaction:
        entry = transaction.locked_book_entry(TableId(TABLE), "account-mozart")

    assert (entry.invitation.id, entry.invitation.ended) == ("invitation", None)


def test_the_store_refuses_an_outcome_without_an_invitation(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")
    update = (
        "UPDATE member_book SET invitation_id = NULL, invitation_expires_at = NULL, owner_account = NULL,"
        " inviter_account = NULL, ended_outcome = 'busy'"
    )

    with pytest.raises(Exception, match="violates check constraint"), before_the_upgrade.begin() as connection:
        connection.execute(text(update))
