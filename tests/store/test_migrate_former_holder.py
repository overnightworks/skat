import pytest
from sqlalchemy import text

from skat.store.migrate import migrate
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
    """A database at 0033 holding a table whose seat 2 was freed before the upgrade."""
    upgrade_to(unmigrated_engine, "0033")
    with unmigrated_engine.begin() as connection:
        for statement in RUNNING_HAND:
            connection.execute(text(statement), {"table": TABLE})
    return unmigrated_engine


def stored(engine):
    with PostgresTableTransactions(engine).begin() as transaction:
        return transaction.table(TableId(TABLE))


def test_a_chair_freed_before_the_upgrade_reads_with_no_former_holder(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")

    record = stored(before_the_upgrade)

    assert record.progress.former_holders == frozenset()
    assert [chair.occupant is None for chair in record.chairs] == [False, True, False]


def test_the_upgrade_runs_twice_and_keeps_the_chairs(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")
    migrate(before_the_upgrade)

    record = stored(before_the_upgrade)

    assert [chair.occupant.display_name for chair in record.chairs if chair.occupant] == ["Anna", "Mozart"]
