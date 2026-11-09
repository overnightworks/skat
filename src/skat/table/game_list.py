from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from skat.engine.deal import SEATS, seats_from
from skat.engine.score import Settlement, overbid, reckon, settle
from skat.engine.tricks import opponents_points_of
from skat.engine.value import breakdown_of, value_of
from skat.table.rules import result_pending

if TYPE_CHECKING:
    from skat.engine.declaration import Declaration
    from skat.engine.tricks import PlayedOut
    from skat.engine.value import Level, Matadors
    from skat.table.records import Occupant, TableRecord


@dataclass(frozen=True)
class ListEntry:
    """One finished game in the table's list: who sat where, what was played, and what it scored.

    Schneider and Schwarz are the levels the valuation counted; the matadors are None exactly in Null. Each seat's
    display name is the one held at the end of the game, None for an entry stored before names were kept.
    """

    seat_accounts: tuple[str, str, str]
    seat_names: tuple[str | None, str | None, str | None]
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
        return opponents_points_of(self.declarer_points)

    @property
    def overbid(self) -> bool:
        return overbid(self.game_value, self.bid)


def _seated(table: TableRecord) -> tuple[Occupant, Occupant, Occupant]:
    occupants = tuple(chair.occupant for chair in table.chairs if chair.occupant is not None)
    # Nobody leaves a chair while a hand runs, so a game ends with three seated people.
    if len(occupants) != len(table.chairs):  # pragma: no cover
        message = f"table {table.id.value} ended a game with a free chair"
        raise RuntimeError(message)
    first, second, third = occupants
    return first, second, third


def list_entry_of(played: PlayedOut, table: TableRecord) -> ListEntry:
    """The entry a played-out game writes: its numbers come from the engine, its seats from the table."""
    declaration = played.declared.declaration
    # Play starts only after the declaration, and the store writes the dealer with the hand.
    if declaration is None or table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} ended a game without a declaration or a dealer"
        raise RuntimeError(message)
    seats = seats_from(table.dealer)
    first, second, third = _seated(table)
    valuation = value_of(played)
    settlement = settle(played, played.declared.bid)
    return ListEntry(
        seat_accounts=(first.account_id, second.account_id, third.account_id),
        seat_names=(first.display_name, second.display_name, third.display_name),
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
    won: bool


@dataclass(frozen=True)
class Standing:
    """One account's place at the end of a series, named as the list last seated it; None if no name was stored."""

    account_id: str
    display_name: str | None
    total: int
    won: int
    lost: int
    place: int


@dataclass(frozen=True)
class ResultView:
    """The last game's result while it stands, the same for every viewer; it names no account and no card."""

    ordinal: int
    declarer_seat: int
    declaration: Declaration
    schneider: bool
    schwarz: bool
    matadors: Matadors | None
    base_value: int | None
    levels: tuple[Level, ...]
    won: bool
    doubled: bool
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
        SeatGain(
            seat,
            reckoning.declarer if seat == entry.declarer_seat else reckoning.each_opponent,
            won=entry.won == (seat == entry.declarer_seat),
        )
        for seat in SEATS
    )


def total_of(game_list: tuple[ListEntry, ...], account_id: str) -> int:
    """What the account has gained over the list, on whichever chair it held in each game."""
    return sum(
        gain.gain for entry in game_list for gain in _gains(entry) if entry.seat_accounts[gain.seat - 1] == account_id
    )


def _standing_without_place(game_list: tuple[ListEntry, ...], account_id: str) -> Standing:
    declared = [entry for entry in game_list if entry.seat_accounts[entry.declarer_seat - 1] == account_id]
    last = next(entry for entry in reversed(game_list) if account_id in entry.seat_accounts)
    won = sum(entry.won for entry in declared)
    name = last.seat_names[last.seat_accounts.index(account_id)]
    return Standing(account_id, name, total_of(game_list, account_id), won, len(declared) - won, place=0)


def _rank_key(standing: Standing) -> tuple[int, int, int]:
    return -standing.total, -standing.won, standing.lost


def standings_of(game_list: tuple[ListEntry, ...]) -> tuple[Standing, ...]:
    """Every account the list seated, ranked by total, then more games won, then fewer lost as declarer.

    Accounts with all three equal share a place, and the next place counts everyone above it.
    """
    accounts = dict.fromkeys(account for entry in game_list for account in entry.seat_accounts)
    standings = sorted((_standing_without_place(game_list, account) for account in accounts), key=_rank_key)
    keys = [_rank_key(each) for each in standings]
    return tuple(replace(each, place=1 + sum(key < _rank_key(each) for key in keys)) for each in standings)


def result_view_of(table: TableRecord) -> ResultView | None:
    """The list's last entry while its result is pending, numbered by its place in the list; None otherwise."""
    if not result_pending(table):
        return None
    entry = table.game_list[-1]
    breakdown = breakdown_of(entry.declaration, schneider=entry.schneider, schwarz=entry.schwarz)
    return ResultView(
        ordinal=len(table.game_list),
        declarer_seat=entry.declarer_seat,
        declaration=entry.declaration,
        schneider=entry.schneider,
        schwarz=entry.schwarz,
        matadors=entry.matadors,
        base_value=breakdown.base_value,
        levels=breakdown.levels,
        won=entry.won,
        doubled=not entry.won,
        overbid=entry.overbid,
        bid=entry.bid,
        game_value=entry.game_value,
        settled_value=entry.settled_value,
        score=entry.score,
        declarer_points=entry.declarer_points,
        opponents_points=entry.opponents_points,
        gains=_gains(entry),
    )
