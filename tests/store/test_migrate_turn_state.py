import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from tests.support.migrations import upgrade_to

pytestmark = pytest.mark.postgres

TABLE = "0123456789abcdef0123456789abcdef"
BEFORE = "0051"


@pytest.fixture
def before_the_upgrade(unmigrated_engine):
    """A database before the turn state, holding a table with a person on chair 1 and an agent on chair 2."""
    upgrade_to(unmigrated_engine, BEFORE)
    with unmigrated_engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES (:table, 7)"), {"table": TABLE})
        connection.execute(text("INSERT INTO series (table_id, number) VALUES (:table, 1)"), {"table": TABLE})
        connection.execute(
            text(
                "INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind) VALUES"
                " (:table, 1, 'account-anna', 'Anna', 'person'), (:table, 2, 'account-mozart', 'Mozart', 'agent'),"
                " (:table, 3, NULL, NULL, NULL)"
            ),
            {"table": TABLE},
        )
    return unmigrated_engine


def turn_states(engine):
    with PostgresTableTransactions(engine).begin() as transaction:
        return [chair.turn_state for chair in transaction.table(TableId(TABLE)).chairs]


def test_every_stored_chair_reads_with_nothing_stated(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")

    assert turn_states(before_the_upgrade) == [None, None, None]


def test_the_release_before_serves_on_the_new_schema_without_naming_the_columns(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")

    with before_the_upgrade.begin() as connection:
        connection.execute(
            text(
                "UPDATE chairs SET account_id = 'account-ben', display_name = 'Ben', occupant_kind = 'person'"
                " WHERE seat = 3"
            )
        )
        connection.execute(
            text("UPDATE chairs SET account_id = NULL, display_name = NULL, occupant_kind = NULL WHERE seat = 2")
        )

    assert turn_states(before_the_upgrade) == [None, None, None]
