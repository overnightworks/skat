from datetime import UTC, datetime

from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CreateTable, Ending, SitDown, TableId
from skat.table.service import TableService
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.played_game import after_the_first_game

NOBODY_CONNECTED = frozenset[str]()
OPENER = Actor(account_id="account-anna", display_name="Anna")
SEATED = (
    OPENER,
    Actor(account_id="account-ben", display_name="Ben"),
    Actor(account_id="account-cleo", display_name="Cleo"),
)


def seated_table(service, name, seats=3, series_length=None):
    """A table with the opener and the next `seats - 1` people seated; the third sitting deals the first hand."""
    table_id = service.create(OPENER, CreateTable(command_id=f"open-{name}", series_length=series_length)).id
    for seat, actor in enumerate(SEATED[1:seats], start=2):
        service.sit(actor, SitDown(f"sit-{name}-{seat}", table_id, seat), NOBODY_CONNECTED)
    return TableId(table_id)


def undealt_table(service, name):
    return seated_table(service, name, seats=2)


def save(transactions, record):
    with transactions.begin() as transaction:
        transaction.save_table(record, played_at=None)


def listed_game(service, transactions, stored, name):
    table_id = seated_table(service, name)
    save(transactions, after_the_first_game(stored(transactions, table_id.value)))
    return table_id


ENDED_AT = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def ended_at(transactions, table_id, ending=None):
    with transactions.begin() as transaction:
        assert transaction.locked_table(table_id) is not None
        transaction.end_table(table_id, ENDED_AT, ending or Ending.empty(DEFAULT_EMPTY_TABLE_SECONDS))


def restarted(database_url):
    engine = create_store_engine(database_url)
    return engine, TableService(PostgresTableTransactions(engine))
