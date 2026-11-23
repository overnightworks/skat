"""Migration 0060 only adds the hand log's two tables: a table the release before wrote keeps its steps where they
were and reads them through the old store until this release writes it.
"""

import pytest
from sqlalchemy import func, select, text

from skat.engine.bidding import Bid
from skat.engine.deal import Position
from skat.store.hand_log import hand_steps, hands
from skat.store.migrate import declares_contraction
from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from tests.support.migrations import migrated_from, revisions_from

pytestmark = pytest.mark.postgres


@pytest.fixture
def migrated(unmigrated_engine):
    return migrated_from(
        unmigrated_engine,
        "0059",
        text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('bid', 8, 2, now())"),
        text("INSERT INTO series (table_id, number, length, deals) VALUES ('bid', 1, 12, 1)"),
        text(
            "INSERT INTO auction_actions (table_id, ordinal, position, action, value)"
            " VALUES ('bid', 1, 'middlehand', 'bid', 18)"
        ),
    )


def test_0060_declares_no_contraction():
    assert not declares_contraction(revisions_from("0060")[0])


def test_the_hand_log_starts_empty(migrated):
    with migrated.connect() as connection:
        counts = [
            connection.execute(select(func.count()).select_from(each)).scalar_one() for each in (hand_steps, hands)
        ]

    assert counts == [0, 0]


def test_a_table_the_release_before_wrote_reads_its_steps_from_the_old_store(migrated):
    with PostgresTableTransactions(migrated).begin() as transaction:
        record = transaction.table(TableId("bid"))

    assert (record.version, record.progress.auction) == (8, (Bid(Position.MIDDLEHAND, 18),))
