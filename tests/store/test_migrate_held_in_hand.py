import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.tables import PostgresTableTransactions, metadata
from skat.table.records import Actor, SitDown, TableId
from skat.table.service import TableService
from tests.support.migrations import run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres

NOBODY = frozenset[str]()
TABLE = "0123456789abcdef0123456789abcdef"
SUITS = "ARRAY['diamonds', 'hearts', 'spades', 'clubs']"
RANKS = "ARRAY['seven', 'eight', 'nine', 'ten', 'jack', 'queen', 'king', 'ace']"
RUNNING_HAND = (
    "INSERT INTO tables (id, version, dealer, last_played_at) VALUES (:table, 9, 2, now())",
    "INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind) VALUES"
    " (:table, 1, 'account-anna', 'Anna', 'person'), (:table, 2, 'account-ben', 'Ben', 'person'),"
    " (:table, 3, 'account-mozart', 'Mozart', 'agent')",
    f"INSERT INTO hand_cards SELECT :table, suit, rank, CASE WHEN number <= 10 THEN 'forehand'"  # noqa: S608 - fixed literals
    " WHEN number <= 20 THEN 'middlehand' WHEN number <= 30 THEN 'rearhand' ELSE 'skat' END"
    f" FROM (SELECT suit, rank, row_number() OVER () AS number FROM unnest({SUITS}) AS suit,"
    f" unnest({RANKS}) AS rank) AS deck",
    "INSERT INTO auction_actions VALUES (:table, 1, 'middlehand', 'pass', NULL)",
)


@pytest.fixture
def migrated(unmigrated_engine):
    """A database at 0030 holding a dealt table with a running hand (chairs occupied, cards stored, a step logged),
    taken to head.
    """
    upgrade_to(unmigrated_engine, "0030")
    with unmigrated_engine.begin() as connection:
        for statement in RUNNING_HAND:
            connection.execute(text(statement), {"table": TABLE})
    upgrade_to(unmigrated_engine, "head")
    return unmigrated_engine


def stored(engine):
    with PostgresTableTransactions(engine).begin() as transaction:
        return transaction.table(TableId(TABLE))


def test_every_chair_keeps_its_occupant_and_reads_with_no_mark(migrated):
    record = stored(migrated)

    assert [chair.occupant.display_name for chair in record.chairs] == ["Anna", "Ben", "Mozart"]
    assert record.progress.seats_held == frozenset()
    assert (record.version, record.dealer) == (9, 2)


def test_the_hand_and_its_steps_read_as_before(migrated):
    record = stored(migrated)

    assert [len(cards) for cards in record.hand.hands.values()] == [10, 10, 10]
    assert (len(record.hand.skat), len(record.progress.auction)) == (2, 1)


def test_a_sit_into_any_open_chair_is_not_barred_for_an_account_that_held_one_before_the_upgrade(migrated):
    run_in_transaction(
        migrated,
        text("UPDATE chairs SET account_id = NULL, display_name = NULL, occupant_kind = NULL WHERE seat IN (1, 2)"),
    )

    sat = TableService(PostgresTableTransactions(migrated)).sit(
        Actor("account-anna", "Anna"), SitDown("command-anna", TABLE, 2), NOBODY
    )

    assert sat.refusal is None


def test_the_migrated_schema_is_the_one_the_store_writes_to(migrated):
    with migrated.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


def test_the_check_refuses_a_null_account_in_the_held_list(migrated):
    refused = text("UPDATE chairs SET held_in_hand = ARRAY['account-anna', NULL] WHERE seat = 1")

    with pytest.raises(IntegrityError):
        run_in_transaction(migrated, refused)
