import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from tests.support.migrations import migrated_from, run_in_transaction

pytestmark = pytest.mark.postgres

TABLE = "0123456789abcdef0123456789abcdef"
SEAT_WITH_A_PLAN = 3
DEAL = text(
    """
    INSERT INTO hand_cards (table_id, suit, rank, holder)
    SELECT :table, suit, rank,
           CASE WHEN number <= 10 THEN 'forehand' WHEN number <= 20 THEN 'middlehand'
                WHEN number <= 30 THEN 'rearhand' ELSE 'skat' END
    FROM (SELECT suit, rank, row_number() OVER () AS number
          FROM (VALUES ('clubs'), ('spades'), ('hearts'), ('diamonds')) AS suits (suit)
          CROSS JOIN (VALUES ('seven'), ('eight'), ('nine'), ('ten'), ('jack'), ('queen'), ('king'), ('ace'))
              AS ranks (rank)) AS cards
    """
).bindparams(table=TABLE)


@pytest.fixture
def migrated(unmigrated_engine):
    """A database migrated from the revision before, holding a dealt table whose auction runs."""
    return migrated_from(
        unmigrated_engine,
        "0056",
        text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES (:table, 4, 1, now())").bindparams(
            table=TABLE
        ),
        text("INSERT INTO series (table_id, number) VALUES (:table, 1)").bindparams(table=TABLE),
        text(
            "INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind) VALUES"
            " (:table, 1, 'account-anna', 'Anna', 'person'), (:table, 2, 'account-ben', 'Ben', 'person'),"
            " (:table, 3, 'account-cleo', 'Cleo', 'person')"
        ).bindparams(table=TABLE),
        DEAL,
    )


def with_a_plan(engine):
    run_in_transaction(
        engine,
        text(
            "INSERT INTO auction_plans (table_id, seat, account_id, kind, value, mode)"
            " VALUES (:table, :seat, 'account-cleo', 'limit', 30, 'ask')"
        ).bindparams(table=TABLE, seat=SEAT_WITH_A_PLAN),
    )


def plan_rows(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT seat FROM auction_plans")).all()


def test_a_table_stored_before_the_plans_reads_with_none(migrated):
    with PostgresTableTransactions(migrated).begin() as transaction:
        table = transaction.table(TableId(TABLE))

    assert table.progress.plans == frozenset()


def test_a_plan_of_the_hand_stored_reads_back(migrated):
    with_a_plan(migrated)

    with PostgresTableTransactions(migrated).begin() as transaction:
        table = transaction.table(TableId(TABLE))

    assert [each.seat for each in table.progress.plans] == [SEAT_WITH_A_PLAN]


def test_a_deal_of_the_release_before_clears_the_plans_on_a_migrated_database(migrated):
    with_a_plan(migrated)

    with migrated.begin() as connection:
        connection.execute(text("DELETE FROM hand_cards WHERE table_id = :table"), {"table": TABLE})
        connection.execute(DEAL)

    assert plan_rows(migrated) == []


def test_the_release_before_ends_a_table_that_holds_a_plan_without_naming_the_plans(migrated):
    with_a_plan(migrated)

    run_in_transaction(migrated, text("DELETE FROM chairs WHERE table_id = :table").bindparams(table=TABLE))

    assert plan_rows(migrated) == []
