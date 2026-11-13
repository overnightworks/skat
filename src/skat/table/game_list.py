from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from skat.engine.bock import bock_factor, bock_settlement
from skat.engine.deal import SEATS, positions_from, seats_from
from skat.engine.kontra import KontraReach, doubled_reckoning, doubled_settlement
from skat.engine.ramsch import ramsch_rules_of, reckon_ramsch
from skat.engine.schieberamsch import push_factor
from skat.engine.score import Reckoning, Settlement, announcement_missed, overbid, settle
from skat.engine.tricks import opponents_points_of
from skat.engine.value import Breakdown, breakdown_of, value_of
from skat.table.hand_state import pushing_of
from skat.table.rules import result_pending

if TYPE_CHECKING:
    from skat.engine.deal import Position
    from skat.engine.declaration import Declaration
    from skat.engine.kontra import Doubling, Word
    from skat.engine.ramsch import RamschPlayedOut
    from skat.engine.tricks import PlayedOut
    from skat.engine.value import Level, Matadors
    from skat.table.records import Occupant, TableOptions, TableRecord


class GameEnding(StrEnum):
    """How a declared game ended, as the table knows it; the engine's ending cannot tell a give-up from a game its
    points decided.
    """

    PLAYED_OUT = "played-out"
    GIVEN_UP = "given-up"
    THROWN_DOWN = "thrown-down"


@dataclass(frozen=True)
class ListEntry:
    """One finished game in the table's list: who sat where, what was played, and what it scored.

    Schneider and Schwarz are the levels the valuation counted; the matadors are None exactly in Null. Each seat's
    display name is the one held at the end of the game, None for an entry stored before names were kept. The score
    is the list score with the Bock factor and the doubling applied; `bock_factor` is 1 outside a Bock game and
    `kontra_word` the last word said, None for a game without one. `ended_by_seat` is the seat whose give-up or
    throw-down ended the game, None exactly when the game was played out.
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
    bock_factor: int
    ending: GameEnding
    ended_by_seat: int | None

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


@dataclass(frozen=True)
class RamschEntry:
    """One finished Ramsch in the table's list, by seat: the card points each seat counted, its list score, the seat
    that took all ten tricks and won by it (None if no seat did or the table scores it as any loser) and whether
    a seat with no trick doubled the loser's score. Each seat's display name is the one held at the end of the game.
    `bock_factor` is the Bock factor the Ramsch ran under, 1 outside a Bock game, and `pushes` the times the skat was
    pushed on unseen; the scores are multiplied by both, a Durchmarsch's too unless the table scores it flat.
    """

    seat_accounts: tuple[str, str, str]
    seat_names: tuple[str | None, str | None, str | None]
    seat_points: tuple[int, int, int]
    seat_scores: tuple[int, int, int]
    durchmarsch_seat: int | None
    jungfrau: bool
    bock_factor: int
    pushes: int


type GameEntry = ListEntry | RamschEntry


def _seated(table: TableRecord) -> tuple[Occupant, Occupant, Occupant]:
    occupants = tuple(chair.occupant for chair in table.chairs if chair.occupant is not None)
    # Every hand command is refused while a chair is open, so a game ends with three seated people.
    if len(occupants) != len(table.chairs):  # pragma: no cover
        message = f"table {table.id.value} ended a game with a free chair"
        raise RuntimeError(message)
    first, second, third = occupants
    return first, second, third


def bock_factor_of(table: TableRecord) -> int:
    """What the table's pending Bock rounds multiply the next game's list score by; 1 without Bock."""
    options = table.options.bock
    return 1 if options is None else bock_factor(table.bock, options.overlap)


def pushes_factor(pushes: int, options: TableOptions) -> int:
    """What `pushes` unseen pushes multiply a Ramsch's list score by at a table with these options; 1 without the
    rule.
    """
    ramsch = options.ramsch
    return 1 if ramsch is None or ramsch.pushing is None else push_factor(pushes, ramsch.pushing)


def list_entry_of(
    played: PlayedOut, table: TableRecord, doubling: Doubling | None, ending: GameEnding, ended_by: Position | None
) -> ListEntry:
    """The entry a finished game writes: its numbers come from the engine, its seats and its ending from the table.

    `ended_by` is the position whose give-up or throw-down ended the game, None for a game played out.

    A Bock game multiplies its list score by the table's Bock factor, and the words said double it after that; a table
    without Kontra has no doubling.
    """
    declaration = played.declared.declaration
    # Play starts only after the declaration, and the store writes the dealer with the hand.
    if declaration is None or table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} ended a game without a declaration or a dealer"
        raise RuntimeError(message)
    seats = seats_from(table.dealer)
    first, second, third = _seated(table)
    valuation = value_of(played, played.declared.bid)
    settlement = settle(played, played.declared.bid)
    if table.options.bock is not None:
        settlement = bock_settlement(settlement, table.bock, table.options.bock.overlap)
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
        bock_factor=bock_factor_of(table),
        ending=ending,
        ended_by_seat=None if ended_by is None else seats[ended_by],
    )


def ramsch_entry_of(played: RamschPlayedOut, table: TableRecord) -> RamschEntry:
    """The entry a Ramsch writes: the engine reckons it by the table's Ramsch options and the Bock factor the Ramsch
    ran under times the factor of its pushes, the table gives the seats. The stage's steps are read before the hand's
    progress goes.
    """
    ramsch = table.options.ramsch
    # A Ramsch is played only at a table that plays one, and the store writes the dealer with the hand.
    if ramsch is None or table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} ended a Ramsch without the setting or a dealer"
        raise RuntimeError(message)
    factor = bock_factor_of(table)
    stage = pushing_of(table)
    pushes = 0 if stage is None else stage.pushes
    reckoning = reckon_ramsch(played, ramsch.reckoning, multiplier=factor * pushes_factor(pushes, table.options))
    positions = positions_from(table.dealer)
    seats = seats_from(table.dealer)
    first, second, third = _seated(table)
    points = tuple(reckoning.counted_points[positions[seat]] for seat in SEATS)
    scores = tuple(reckoning.gains[positions[seat]] for seat in SEATS)
    return RamschEntry(
        seat_accounts=(first.account_id, second.account_id, third.account_id),
        seat_names=(first.display_name, second.display_name, third.display_name),
        seat_points=(points[0], points[1], points[2]),
        seat_scores=(scores[0], scores[1], scores[2]),
        durchmarsch_seat=None if reckoning.durchmarsch is None else seats[reckoning.durchmarsch],
        jungfrau=reckoning.jungfrau,
        bock_factor=factor,
        pushes=pushes,
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
    bock_factor: int
    ending: GameEnding
    ended_by_seat: int | None


@dataclass(frozen=True)
class RamschSeatResult:
    """What one seat counted and scored in a Ramsch."""

    seat: int
    points: int
    score: int


@dataclass(frozen=True)
class RamschResultView:
    """The last Ramsch's result while it stands, the same for every viewer; it names no account and no card. `pushes`
    is how often the skat was pushed on unseen and `push_factor` what that made of the scores, beside the Bock factor;
    a Durchmarsch the table scores flat took no push, so its `push_factor` is 1. `divided_by_ten` says the loser's
    eyes were divided by ten before the factors, as the table scores them.
    """

    ordinal: int
    seats: tuple[RamschSeatResult, ...]
    durchmarsch_seat: int | None
    jungfrau: bool
    bock_factor: int
    pushes: int
    push_factor: int
    divided_by_ten: bool


def _reckoning_of(entry: ListEntry, reach: KontraReach) -> Reckoning:
    settlement = Settlement(won=entry.won, value=entry.settled_value, score=entry.score)
    return doubled_reckoning(settlement, entry.kontra_word, reach)


def _gains(entry: GameEntry, reach: KontraReach) -> tuple[SeatGain, ...]:
    """What the game adds to each seat's total; a Ramsch's gains are its seat scores, whatever the table's Kontra
    reach, and only a Durchmarsch that wins is a won game.
    """
    if isinstance(entry, RamschEntry):
        return tuple(SeatGain(seat, entry.seat_scores[seat - 1], won=entry.durchmarsch_seat == seat) for seat in SEATS)
    reckoning = _reckoning_of(entry, reach)
    return tuple(
        SeatGain(
            seat,
            reckoning.declarer if seat == entry.declarer_seat else reckoning.each_opponent,
            won=entry.won == (seat == entry.declarer_seat),
        )
        for seat in SEATS
    )


def total_of(game_list: tuple[GameEntry, ...], account_id: str, reach: KontraReach) -> int:
    """What the account has gained over the list, on whichever chair it held in each game."""
    return sum(
        gain.gain
        for entry in game_list
        for gain in _gains(entry, reach)
        if entry.seat_accounts[gain.seat - 1] == account_id
    )


def _standing_without_place(game_list: tuple[GameEntry, ...], account_id: str, reach: KontraReach) -> Standing:
    """Won and lost count the games the account declared; a Ramsch has no declarer, so it adds to the total alone."""
    declared = [
        entry
        for entry in game_list
        if isinstance(entry, ListEntry) and entry.seat_accounts[entry.declarer_seat - 1] == account_id
    ]
    last = next(entry for entry in reversed(game_list) if account_id in entry.seat_accounts)
    won = sum(entry.won for entry in declared)
    name = last.seat_names[last.seat_accounts.index(account_id)]
    return Standing(account_id, name, total_of(game_list, account_id, reach), won, len(declared) - won, place=0)


def _rank_key(standing: Standing) -> tuple[int, int, int]:
    return -standing.total, -standing.won, standing.lost


def standings_of(game_list: tuple[GameEntry, ...], reach: KontraReach) -> tuple[Standing, ...]:
    """Every account the list seated, ranked by total, then more games won, then fewer lost as declarer.

    Accounts with all three equal share a place, and the next place counts everyone above it.
    """
    accounts = dict.fromkeys(account for entry in game_list for account in entry.seat_accounts)
    standings = sorted((_standing_without_place(game_list, account, reach) for account in accounts), key=_rank_key)
    keys = [_rank_key(each) for each in standings]
    return tuple(replace(each, place=1 + sum(key < _rank_key(each) for key in keys)) for each in standings)


def result_view_of(table: TableRecord) -> ResultView | RamschResultView | None:
    """The list's last entry while its result is pending, numbered by its place in the list; None otherwise."""
    if not result_pending(table):
        return None
    entry = table.game_list[-1]
    ordinal = len(table.game_list)
    if isinstance(entry, RamschEntry):
        ramsch = table.options.ramsch
        rules = None if ramsch is None else ramsch_rules_of(ramsch.reckoning, swept=entry.durchmarsch_seat is not None)
        return RamschResultView(
            ordinal=ordinal,
            seats=tuple(
                RamschSeatResult(seat, entry.seat_points[seat - 1], entry.seat_scores[seat - 1]) for seat in SEATS
            ),
            durchmarsch_seat=entry.durchmarsch_seat,
            jungfrau=entry.jungfrau,
            bock_factor=entry.bock_factor,
            pushes=entry.pushes,
            push_factor=pushes_factor(entry.pushes, table.options) if rules is None or rules.multiplied else 1,
            divided_by_ten=rules is not None and rules.divided_by_ten,
        )
    breakdown = entry.breakdown
    reach = reach_of(table.options)
    reckoning = _reckoning_of(entry, reach)
    return ResultView(
        ordinal=ordinal,
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
        bock_factor=entry.bock_factor,
        ending=entry.ending,
        ended_by_seat=entry.ended_by_seat,
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
    bock_factor: int


@dataclass(frozen=True)
class RamschSeriesSeat:
    """One seat of a Ramsch's row: the name stored with the game (None for an entry stored before names were kept)
    and the seat's list score.
    """

    name: str | None
    score: int


@dataclass(frozen=True)
class RamschSeriesEntryView:
    """One finished Ramsch in the table's list, the same for every viewer: its place, each seat's stored name and
    score, whether a seat took all ten tricks and won by it, whether a Jungfrau doubled the loser's score, and how often
    the skat was pushed on unseen with the factor that made of the scores. It names no account and no card.
    """

    number: int
    seats: tuple[RamschSeriesSeat, ...]
    durchmarsch: bool
    jungfrau: bool
    bock_factor: int
    pushes: int
    push_factor: int


def _series_entry_view_of(
    number: int, entry: GameEntry, options: TableOptions
) -> SeriesEntryView | RamschSeriesEntryView:
    if isinstance(entry, RamschEntry):
        return RamschSeriesEntryView(
            number=number,
            seats=tuple(
                RamschSeriesSeat(name, score) for name, score in zip(entry.seat_names, entry.seat_scores, strict=True)
            ),
            durchmarsch=entry.durchmarsch_seat is not None,
            jungfrau=entry.jungfrau,
            bock_factor=entry.bock_factor,
            pushes=entry.pushes,
            push_factor=pushes_factor(entry.pushes, options),
        )
    return SeriesEntryView(
        number=number,
        declarer_name=entry.seat_names[entry.declarer_seat - 1],
        declaration=entry.declaration,
        levels=entry.levels,
        settled_value=entry.settled_value,
        score=entry.score,
        kontra_word=entry.kontra_word,
        bock_factor=entry.bock_factor,
    )


def series_list_view_of(table: TableRecord) -> tuple[SeriesEntryView | RamschSeriesEntryView, ...]:
    """One row per finished game of the table, numbered from 1 in the order played."""
    return tuple(_series_entry_view_of(number, entry, table.options) for number, entry in enumerate(table.game_list, 1))
