import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from tests.support.migrations import upgrade_to

pytestmark = pytest.mark.postgres

TABLE = "0123456789abcdef0123456789abcdef"
RUNNING_HAND = (
    "INSERT INTO tables (id, version, dealer, last_played_at) VALUES (:table, 9, 2, now())",
    "INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind) VALUES"
    " (:table, 1, 'account-anna', 'Anna', 'person'), (:table, 2, NULL, NULL, NULL),"
    " (:table, 3, 'account-mozart', 'Mozart', 'agent')",
)


@pytest.fixture
def before_the_upgrade(unmigrated_engine):
    """A database at 0036 holding a table whose seat 2 is open."""
    upgrade_to(unmigrated_engine, "0036")
    with unmigrated_engine.begin() as connection:
        for statement in RUNNING_HAND:
            connection.execute(text(statement), {"table": TABLE})
    return unmigrated_engine


def test_a_table_stored_before_the_upgrade_reads_with_no_proposal_and_no_aborted_hand(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")

    with PostgresTableTransactions(before_the_upgrade).begin() as transaction:
        record = transaction.table(TableId(TABLE))

    assert (record.progress.abort_yes, record.progress.aborted) == (frozenset(), False)


@pytest.mark.parametrize(
    "update",
    [
        pytest.param(
            "UPDATE tables SET abort_yes_seats = '{4}' WHERE id = :table",
            id="a-vote-of-a-seat-the-table-does-not-have",
        ),
        pytest.param(
            "UPDATE tables SET abort_yes_seats = '{1}', hand_aborted = true WHERE id = :table",
            id="a-proposal-beside-an-aborted-hand",
        ),
    ],
)
def test_the_store_refuses_a_proposal_that_is_no_proposal(before_the_upgrade, update):
    upgrade_to(before_the_upgrade, "head")

    with pytest.raises(Exception, match="violates check constraint"), before_the_upgrade.begin() as connection:
        connection.execute(text(update), {"table": TABLE})
