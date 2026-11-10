from typing import TYPE_CHECKING

from skat.engine.bidding import Declared, auction_after
from skat.engine.declaration import Declaring, declaring_after
from skat.engine.kontra import Doubling, bidders_of, doubling_after
from skat.engine.tricks import playing_after, start_play

if TYPE_CHECKING:
    from skat.engine.bidding import Auction
    from skat.engine.tricks import Playing
    from skat.table.records import TableRecord


def auction_of(table: TableRecord) -> Auction:
    """The auction of a table, replayed through the engine from its stored steps."""
    return auction_after(table.progress.auction)


def declaring_of(table: TableRecord) -> Declaring | None:
    """The declarer's stored steps replayed through the engine; None while the auction has no declarer."""
    result = auction_of(table).result
    if table.hand is None or not isinstance(result, Declared):
        return None
    return declaring_after(Declaring.start(result, table.hand), table.progress.declaring)


def _play_start(table: TableRecord) -> Playing | None:
    declared = declaring_of(table)
    if table.hand is None or declared is None or declared.declaration is None:
        return None
    return start_play(declared, table.hand)


def playing_of(table: TableRecord) -> Playing | None:
    """The cards played so far replayed through the engine; None until the game is declared."""
    start = _play_start(table)
    return None if start is None else playing_after(start, table.progress.plays)


def doubling_of(table: TableRecord) -> Doubling | None:
    """The words of the running hand replayed through the engine, each against the cards it followed; None while no
    game is played or the table plays without Kontra.
    """
    start, options = _play_start(table), table.options.kontra
    if start is None or options is None:
        return None
    bidders = bidders_of(table.progress.auction)
    return doubling_after(start, table.progress.plays, table.progress.words, options, bidders)
