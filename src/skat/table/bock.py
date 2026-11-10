from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.bock import BockRounds, TotalChange, advance, bock_triggered, games_left
from skat.engine.kontra import Doubling
from skat.table.game_list import bock_factor_of, reach_of, total_of
from skat.table.hand_state import doubling_of
from skat.table.rules import series_games_left

if TYPE_CHECKING:
    from skat.engine.bidding import PassedIn
    from skat.engine.tricks import PlayedOut
    from skat.table.game_list import ListEntry
    from skat.table.records import TableRecord


@dataclass(frozen=True)
class BockView:
    """The Bock games still to come, the running one included, and what the running or next game's list score is
    multiplied by; the same for every viewer.
    """

    games_left: int
    factor: int


def _total_changes(table: TableRecord, entry: ListEntry) -> tuple[TotalChange, ...]:
    reach = reach_of(table.options)
    accounts = (chair.occupant.account_id for chair in table.chairs if chair.occupant is not None)
    return tuple(
        TotalChange(total_of(table.game_list, account, reach), total_of((*table.game_list, entry), account, reach))
        for account in accounts
    )


def bock_after(table: TableRecord, ended: PlayedOut | PassedIn, entry: ListEntry | None) -> BockRounds:
    """The pending Bock rounds once the table's running hand has ended; `entry` is the hand's list entry, None for a
    passed-in hand, which leaves none.

    The hand uses up a Bock game and meets the table's triggers; the series' last game lets every round lapse.
    """
    options = table.options.bock
    series_ends_with_this_hand = series_games_left(table) == 1  # the running hand counts as a game left
    if options is None or series_ends_with_this_hand:
        return BockRounds.start()
    totals = () if entry is None else _total_changes(table, entry)
    triggered = bock_triggered(options.triggers, ended, doubling_of(table) or Doubling.start(), totals)
    return advance(table.bock, options.overlap, triggered=triggered)


def bock_view_of(table: TableRecord) -> BockView | None:
    """The pending games for any viewer; None at a table without Bock.

    The games left are capped by the games the series still deals.
    """
    options = table.options.bock
    if options is None:
        return None
    left = games_left(table.bock, options.overlap)
    series_left = series_games_left(table)
    if series_left is not None:
        left = min(left, series_left)
    return BockView(left, bock_factor_of(table))
