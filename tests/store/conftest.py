import random
import secrets

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
def operator_account_id():
    return f"account-{secrets.token_hex(8)}"


@pytest.fixture
def unmigrated_engine(unmigrated_database_url):
    engine = create_store_engine(unmigrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def transactions(engine):
    return PostgresTableTransactions(engine)


@pytest.fixture
def service(transactions):
    return TableService(transactions, random_source=random.Random(8))  # noqa: S311 - a seeded source makes the deal reproducible


@pytest.fixture
def stored():
    """The reader of a table as a transactions port holds it; a restart test hands it the port it restarted."""

    def read(transactions, table_id):
        with transactions.begin() as transaction:
            return transaction.table(TableId(table_id))

    return read
