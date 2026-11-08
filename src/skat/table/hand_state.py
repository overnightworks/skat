from typing import TYPE_CHECKING

from skat.engine.bidding import auction_after

if TYPE_CHECKING:
    from skat.engine.bidding import Auction
    from skat.table.records import TableRecord


def auction_of(table: TableRecord) -> Auction:
    """The auction of a table, replayed through the engine from its stored steps."""
    return auction_after(table.progress.auction)
