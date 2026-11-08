import random

import pytest

from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from skat.table.service import TableService


@pytest.fixture
def engine(database_url):
    engine = create_store_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def transactions(engine):
    return PostgresTableTransactions(engine)


@pytest.fixture
def service(transactions):
    return TableService(transactions, random_source=random.Random(8))  # noqa: S311 - a seeded source makes the deal reproducible


def stored(transactions, table_id):
    with transactions.begin() as transaction:
        return transaction.table(TableId(table_id))
