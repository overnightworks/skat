"""The moment of a seat at its table, decided from the seat's own view like `awaiting`, so that what the seat is
offered and what its view shows cannot disagree.

A moment names what a seat may do, not whether it is on turn: the seats of the auction share one moment, and so do the
seats of a game's play. Only the declarer's steps tell the declarer from the opponents, who wait for it and share the
moment of a seat with nothing yet to do.
"""

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skat.table.views import HandView, TableView

__all__ = ["TableMoment", "moment_of"]


class TableMoment(StrEnum):
    """What a seat may do now; `LOBBY` is the moment of an account that holds no chair."""

    LOBBY = "lobby"
    WAITING = "waiting"
    AUCTION = "auction"
    DECLARING = "declaring"
    PUSHING = "pushing"
    PLAYING = "playing"
    OPEN_CHAIR = "open_chair"
    RESULT = "result"
    SERIES_END = "series_end"


def moment_of(view: TableView) -> TableMoment:
    """The moment of the viewer's seat at the live table in `view`."""
    hand = view.hand
    if hand is None:
        return _between_hands(view)
    if hand.waiting_seat is not None:
        return TableMoment.OPEN_CHAIR
    if hand.pushing is not None:
        return TableMoment.PUSHING
    if hand.playing is not None:
        return TableMoment.PLAYING
    if hand.declaring is not None:
        return TableMoment.DECLARING if _is_the_declarer(view, hand) else TableMoment.WAITING
    return TableMoment.AUCTION


def _between_hands(view: TableView) -> TableMoment:
    if view.series is not None and view.series.over:
        return TableMoment.SERIES_END
    return TableMoment.RESULT if view.result is not None else TableMoment.WAITING


def _is_the_declarer(view: TableView, hand: HandView) -> bool:
    own = next((chair for chair in view.chairs if chair.is_mine), None)
    return own is not None and hand.declaring is not None and hand.declaring.declarer_seat == own.seat
