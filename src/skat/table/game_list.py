from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.deal import SEATS, seats_from
from skat.engine.score import Settlement, overbid, reckon, settle
from skat.engine.tricks import ALL_POINTS
from skat.engine.value import value_of
from skat.table.rules import result_pending

if TYPE_CHECKING:
    from skat.engine.declaration import Declaration
    from skat.engine.tricks import PlayedOut
    from skat.engine.value import Matadors
    from skat.table.records import TableRecord


@dataclass(frozen=True)
class ListEntry:
    """One finished game in the table's list: who sat where, what was played, and what it scored.

    Schneider and Schwarz are the levels the valuation counted; the matadors are None exactly in Null.
    """

    seat_accounts: tuple[str, str, str]
    declarer_seat: int
    declaration: Declaration
    schneider: bool
    schwarz: bool
    matadors: Matadors | None
    won: bool
    bid: int
    game_value: int
    settled_value: int
    score: int
    declarer_points: int

    @property
    def opponents_points(self) -> int:
        return ALL_POINTS - self.declarer_points

    @property
    def overbid(self) -> bool:
        return overbid(self.game_value, self.bid)


def _seat_accounts(table: TableRecord) -> tuple[str, str, str]:
    accounts = tuple(chair.occupant.account_id for chair in table.chairs if chair.occupant is not None)
    # Nobody leaves a chair while a hand runs, so a game ends with three seated people.
    if len(accounts) != len(table.chairs):  # pragma: no cover
        message = f"table {table.id.value} ended a game with a free chair"
        raise RuntimeError(message)
    first, second, third = accounts
    return first, second, third


def list_entry_of(played: PlayedOut, table: TableRecord) -> ListEntry:
    """The entry a played-out game writes: its numbers come from the engine, its seats from the table."""
    declaration = played.declared.declaration
    # Play starts only after the declaration, and the store writes the dealer with the hand.
    if declaration is None or table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} ended a game without a declaration or a dealer"
        raise RuntimeError(message)
    seats = seats_from(table.dealer)
    valuation = value_of(played)
    settlement = settle(played, played.declared.bid)
    return ListEntry(
        seat_accounts=_seat_accounts(table),
        declarer_seat=seats[played.declared.declarer],
        declaration=declaration,
        schneider=valuation.schneider,
        schwarz=valuation.schwarz,
        matadors=valuation.matadors,
        won=settlement.won,
        bid=played.declared.bid,
        game_value=valuation.value,
        settled_value=settlement.value,
        score=settlement.score,
        declarer_points=played.declarer_points,
    )


@dataclass(frozen=True)
class SeatGain:
    """What a game adds to one chair's total."""

    seat: int
    gain: int


@dataclass(frozen=True)
class ResultView:
    """The last game's result while it stands, the same for every viewer; it names no account and no card."""

    ordinal: int
    declarer_seat: int
    declaration: Declaration
    schneider: bool
    schwarz: bool
    matadors: Matadors | None
    won: bool
    overbid: bool
    bid: int
    game_value: int
    settled_value: int
    score: int
    declarer_points: int
    opponents_points: int
    gains: tuple[SeatGain, ...]


def _gains(entry: ListEntry) -> tuple[SeatGain, ...]:
    reckoning = reckon(Settlement(won=entry.won, value=entry.settled_value, score=entry.score))
    return tuple(
        SeatGain(seat, reckoning.declarer if seat == entry.declarer_seat else reckoning.each_opponent) for seat in SEATS
    )


def total_of(game_list: tuple[ListEntry, ...], account_id: str) -> int:
    """What the account has gained over the list, on whichever chair it held in each game."""
    return sum(
        gain.gain for entry in game_list for gain in _gains(entry) if entry.seat_accounts[gain.seat - 1] == account_id
    )


def result_view_of(table: TableRecord) -> ResultView | None:
    """The list's last entry while its result is pending, numbered by its place in the list; None otherwise."""
    if not result_pending(table):
        return None
    entry = table.game_list[-1]
    return ResultView(
        ordinal=len(table.game_list),
        declarer_seat=entry.declarer_seat,
        declaration=entry.declaration,
        schneider=entry.schneider,
        schwarz=entry.schwarz,
        matadors=entry.matadors,
        won=entry.won,
        overbid=entry.overbid,
        bid=entry.bid,
        game_value=entry.game_value,
        settled_value=entry.settled_value,
        score=entry.score,
        declarer_points=entry.declarer_points,
        opponents_points=entry.opponents_points,
        gains=_gains(entry),
    )
