from contextlib import nullcontext
from dataclasses import replace

from sqlalchemy import func, update

from skat.store.schema import tables
from skat.table.records import Ending, EndReason, HandProgress, Series, TableId

EMPTY_SECONDS = 0
POSTGRES_EMPTY_SECONDS = 1
OLD_CLOSER = "Anna"


def end_the_table(service, table_id, empty_seconds=EMPTY_SECONDS):
    """End the live table nobody was dealt a hand at, as the server ends one nobody came to."""
    ended = service.end_empty_table(TableId(table_id), nullcontext(frozenset()), empty_seconds)
    assert ended


def lapse_the_empty_wait(engine, table_id):
    """Make the wait of a table in Postgres up: its stamp is the database clock's, so it is moved back."""
    with engine.begin() as connection:
        connection.execute(
            update(tables)
            .where(tables.c.id == str(table_id))
            .values(empty_since=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, POSTGRES_EMPTY_SECONDS + 1))
        )


def be_at_the_series_end(store, table_id):
    """The table after its series' last game, in the in-memory store: no hand and no game left to deal."""
    record = store.tables[table_id]
    store.tables[table_id] = replace(record, hand=None, progress=HandProgress(), series=Series(12, 12))


def end_as_an_opener_closed_it(transactions, table_id, at, closed_by_name=OLD_CLOSER):
    """Write the tombstone an opener's close left, which stored tables still carry."""
    with transactions.begin() as transaction:
        transaction.end_table(TableId(table_id), at, Ending(EndReason.CLOSED, closed_by_name=closed_by_name))
