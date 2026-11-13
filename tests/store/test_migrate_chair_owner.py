import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import migrate
from skat.store.tables import PostgresTableTransactions
from skat.table.records import OccupantKind, TableId
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

TABLE = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def before_the_upgrade(unmigrated_engine):
    """A database at 0033 holding a table with a person, an agent and a free chair."""
    upgrade_to(unmigrated_engine, "0033")
    with unmigrated_engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES (:table, 7)"), {"table": TABLE})
        connection.execute(
            text(
                "INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind) VALUES"
                " (:table, 1, 'account-anna', 'Anna', 'person'), (:table, 2, 'account-mozart', 'Mozart', 'agent'),"
                " (:table, 3, NULL, NULL, NULL)"
            ),
            {"table": TABLE},
        )
    return unmigrated_engine


@pytest.fixture
def migrated(before_the_upgrade):
    upgrade_to(before_the_upgrade, "head")
    return before_the_upgrade


def occupants(engine):
    with PostgresTableTransactions(engine).begin() as transaction:
        return [chair.occupant for chair in transaction.table(TableId(TABLE)).chairs]


def test_every_stored_chair_reads_as_before_with_no_owner(migrated):
    anna, mozart, free = occupants(migrated)

    assert [(anna.display_name, anna.kind), (mozart.display_name, mozart.kind), free] == [
        ("Anna", OccupantKind.PERSON),
        ("Mozart", OccupantKind.AGENT),
        None,
    ]
    assert (anna.owner_account, mozart.owner_account) == (None, None)


def test_a_second_run_of_the_migration_reads_the_same_chairs(migrated):
    before = occupants(migrated)

    migrate(migrated)

    assert occupants(migrated) == before


def test_an_agent_chair_takes_an_owner(migrated):
    run_in_transaction(migrated, text("UPDATE chairs SET owner_account = 'account-felix' WHERE seat = 2"))

    assert occupants(migrated)[1].owner_account == "account-felix"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE chairs SET owner_account = 'account-felix' WHERE seat = 1",
        "UPDATE chairs SET owner_account = 'account-felix' WHERE seat = 3",
    ],
    ids=["a person's chair", "a free chair"],
)
def test_the_check_refuses_an_owner_on_a_chair_no_agent_holds(migrated, statement):
    with pytest.raises(IntegrityError):
        run_in_transaction(migrated, text(statement))
