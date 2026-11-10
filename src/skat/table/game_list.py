from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from skat.engine.deal import SEATS, seats_from
from skat.engine.kontra import KontraReach, doubled_reckoning, doubled_settlement
from skat.engine.score import Reckoning, Settlement, announcement_missed, overbid, settle
from skat.engine.tricks import opponents_points_of
from skat.engine.value import Breakdown, breakdown_of, value_of
from skat.table.rules import result_pending

if TYPE_CHECKING:
    from skat.engine.declaration import Declaration
    from skat.engine.kontra import Doubling, Word
    from skat.engine.tricks import PlayedOut
    from skat.engine.value import Level, Matadors
    from skat.table.records import Occupant, TableOptions, TableRecord


@dataclass(frozen=True)
class ListEntry:
    """One finished game in the table's list: who sat where, what was played, and what it scored.

    Schneider and Schwarz are the levels the valuation counted; the matadors are None exactly in Null. Each seat's
    display name is the one held at the end of the game, None for an entry stored before names were kept. The score
    is the list score with the doubling applied; `kontra_word` is the last word said, None for a game without one.
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
    kontra_word: Word | None

    @property
    def opponents_points(self) -> int:
        return opponents_points_of(self.declarer_points)

    @property
    def overbid(self) -> bool:
        return overbid(self.game_value, self.bid)

    @property
    def breakdown(self) -> Breakdown:
        return breakdown_of(self.declaration, self.matadors, schneider=self.schneider, schwarz=self.schwarz)

    @property
    def levels(self) -> tuple[Level, ...]:
        return self.breakdown.levels


def _seated(table: TableRecord) -> tuple[Occupant, Occupant, Occupant]:
    occupants = tuple(chair.occupant for chair in table.chairs if chair.occupant is not None)
    # Nobody leaves a chair while a hand runs, so a game ends with three seated people.
    if len(occupants) != len(table.chairs):  # pragma: no cover
        message = f"table {table.id.value} ended a game with a free chair"
        raise RuntimeError(message)
    first, second, third = occupants
    return first, second, third


def list_entry_of(played: PlayedOut, table: TableRecord, doubling: Doubling | None) -> ListEntry:
    """The entry a played-out game writes: its numbers come from the engine, its seats from the table.

    The words said double its list score; a table without Kontra has no doubling.
    """
    declaration = played.declared.declaration
    # Play starts only after the declaration, and the store writes the dealer with the hand.
    if declaration is None or table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} ended a game without a declaration or a dealer"
        raise RuntimeError(message)
    seats = seats_from(table.dealer)
    first, second, third = _seated(table)
    valuation = value_of(played)
    settlement = settle(played, played.declared.bid)
    if doubling is not None:
        settlement = doubled_settlement(settlement, doubling)
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
        kontra_word=None if doubling is None else doubling.last_word,
    )


def reach_of(options: TableOptions) -> KontraReach:
    """What the doubling of the standings follows; a table without Kontra has no word to double by."""
    return KontraReach.KONTRA_RE if options.kontra is None else options.kontra.reach


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
class KontraResult:
    """The last word said in the game and the factor it made."""

    word: Word
    factor: int


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
    multiplier: int | None
    list_bonus: int
    announcement_missed: bool
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
    kontra: KontraResult | None


def _reckoning_of(entry: ListEntry, reach: KontraReach) -> Reckoning:
    settlement = Settlement(won=entry.won, value=entry.settled_value, score=entry.score)
    return doubled_reckoning(settlement, entry.kontra_word, reach)


def _gains(entry: ListEntry, reach: KontraReach) -> tuple[SeatGain, ...]:
    reckoning = _reckoning_of(entry, reach)
    return tuple(
        SeatGain(
            seat,
            reckoning.declarer if seat == entry.declarer_seat else reckoning.each_opponent,
            won=entry.won == (seat == entry.declarer_seat),
        )
        for seat in SEATS
    )


def total_of(game_list: tuple[ListEntry, ...], account_id: str, reach: KontraReach) -> int:
    """What the account has gained over the list, on whichever chair it held in each game."""
    return sum(
        gain.gain
        for entry in game_list
        for gain in _gains(entry, reach)
        if entry.seat_accounts[gain.seat - 1] == account_id
    )


def _standing_without_place(game_list: tuple[ListEntry, ...], account_id: str, reach: KontraReach) -> Standing:
    declared = [entry for entry in game_list if entry.seat_accounts[entry.declarer_seat - 1] == account_id]
    last = next(entry for entry in reversed(game_list) if account_id in entry.seat_accounts)
    won = sum(entry.won for entry in declared)
    name = last.seat_names[last.seat_accounts.index(account_id)]
    return Standing(account_id, name, total_of(game_list, account_id, reach), won, len(declared) - won, place=0)


def _rank_key(standing: Standing) -> tuple[int, int, int]:
    return -standing.total, -standing.won, standing.lost


def standings_of(game_list: tuple[ListEntry, ...], reach: KontraReach) -> tuple[Standing, ...]:
    """Every account the list seated, ranked by total, then more games won, then fewer lost as declarer.

    Accounts with all three equal share a place, and the next place counts everyone above it.
    """
    accounts = dict.fromkeys(account for entry in game_list for account in entry.seat_accounts)
    standings = sorted((_standing_without_place(game_list, account, reach) for account in accounts), key=_rank_key)
    keys = [_rank_key(each) for each in standings]
    return tuple(replace(each, place=1 + sum(key < _rank_key(each) for key in keys)) for each in standings)


def result_view_of(table: TableRecord) -> ResultView | None:
    """The list's last entry while its result is pending, numbered by its place in the list; None otherwise."""
    if not result_pending(table):
        return None
    entry = table.game_list[-1]
    breakdown = entry.breakdown
    reach = reach_of(table.options)
    reckoning = _reckoning_of(entry, reach)
    return ResultView(
        ordinal=len(table.game_list),
        declarer_seat=entry.declarer_seat,
        declaration=entry.declaration,
        schneider=entry.schneider,
        schwarz=entry.schwarz,
        matadors=entry.matadors,
        base_value=breakdown.base_value,
        levels=breakdown.levels,
        multiplier=breakdown.multiplier,
        list_bonus=reckoning.declarer - entry.score,
        announcement_missed=announcement_missed(entry.declaration.announcement, won=entry.won, overbid=entry.overbid),
        won=entry.won,
        doubled=not entry.won,
        overbid=entry.overbid,
        bid=entry.bid,
        game_value=entry.game_value,
        settled_value=entry.settled_value,
        score=entry.score,
        declarer_points=entry.declarer_points,
        opponents_points=entry.opponents_points,
        gains=_gains(entry, reach),
        kontra=None if entry.kontra_word is None else KontraResult(entry.kontra_word, entry.kontra_word.factor),
    )


@dataclass(frozen=True)
class SeriesEntryView:
    """One finished game in the table's list, the same for every viewer: its place, its declarer by the name stored
    with the game (None for an entry stored before names were kept), the game, its levels, its value and the
    declarer's gain or loss. It names no account and no card.
    """

    number: int
    declarer_name: str | None
    declaration: Declaration
    levels: tuple[Level, ...]
    settled_value: int
    score: int
    kontra_word: Word | None


def series_list_view_of(table: TableRecord) -> tuple[SeriesEntryView, ...]:
    """One row per finished game of the table, numbered from 1 in the order played."""
    return tuple(
        SeriesEntryView(
            number=number,
            declarer_name=entry.seat_names[entry.declarer_seat - 1],
            declaration=entry.declaration,
            levels=entry.levels,
            settled_value=entry.settled_value,
            score=entry.score,
            kontra_word=entry.kontra_word,
        )
        for number, entry in enumerate(table.game_list, 1)
    )
