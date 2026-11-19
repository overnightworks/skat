from contextlib import nullcontext
from dataclasses import replace

from skat.table.records import Ending, EndReason, HandProgress, Series, TableId

EMPTY_SECONDS = 60
OLD_CLOSER = "Anna"


def end_the_table(service, table_id):
    """End the live table nobody was dealt a hand at, as the server ends one nobody came to."""
    ended = service.end_empty_table(TableId(table_id), nullcontext(frozenset()), EMPTY_SECONDS)
    assert ended


def be_at_the_series_end(store, table_id):
    """The table after its series' last game, in the in-memory store: no hand and no game left to deal."""
    record = store.tables[table_id]
    store.tables[table_id] = replace(record, hand=None, progress=HandProgress(), series=Series(12, 12))


def end_as_an_opener_closed_it(transactions, table_id, at):
    """Write the tombstone an opener's close left, which stored tables still carry."""
    with transactions.begin() as transaction:
        transaction.end_table(TableId(table_id), at, Ending(EndReason.CLOSED, closed_by_name=OLD_CLOSER))
