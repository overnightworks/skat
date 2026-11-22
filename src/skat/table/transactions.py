from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

from skat.table.member_place import MemberBook
from skat.table.member_view import traces_after

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from skat.table.game_cards import GameCards
    from skat.table.records import Chair, EndedTable, Ending, Receipt, Replay, TableId, TableRecord

__all__ = [
    "DuplicateReceiptError",
    "HeldChair",
    "LiveWait",
    "OccupiedChair",
    "PausedFacts",
    "TableTransaction",
    "TableTransactions",
    "save_traced",
]


class DuplicateReceiptError(Exception):
    """Another transaction stored a receipt under the same (account, command id) first."""


def retried_on_duplicate_receipt[T](attempt: Callable[[], T]) -> T:
    """Run the command; when the same command id committed meanwhile, the second run finds that receipt and replays
    it or refuses the reuse.
    """
    try:
        return attempt()
    except DuplicateReceiptError:
        return attempt()


class TableTransaction(MemberBook, Protocol):  # pragma: no cover - a port's method bodies are signatures
    def replay(self, account_id: str, command_id: str) -> Replay | None: ...

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None: ...

    def game_cards(self, table_id: TableId, series_number: int, number: int) -> GameCards | None:
        """The cards of the `number`th game of the table's series `series_number`; None for a game stored without
        them, and for a number no game has.
        """
        ...

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        """A live table, its row locked exclusively for the transaction; only the commands that change it read this
        way. An ended table reads as none.
        """
        ...

    def save_table(self, table: TableRecord, *, played_at: datetime | None) -> None:
        """Write the table's version, chairs and dealer, a new hand's cards and steps, and new list entries.

        `played_at` is the time of the deal or step of play this save records and is written in the same statement
        as the dealer; None leaves the stored time as it is, so a save that deals a hand with none is refused. A new
        list entry is written with the cards it carries, in the same transaction.

        A passed-in hand's cards go and its steps stay until the next deal; a played-out hand, a record without a
        hand whose list grew, loses its cards and every step before its entry is appended. A stored hand stays as
        dealt: a record whose hand differs from it while the hand has progress raises, unless the third pass ended
        the hand of a table without Ramsch. A list that does not continue the stored one raises, unless the record is
        of a later series than the stored one: the stored rows of the earlier series stay and the table reads only
        its current series; a free chair that is ready raises too.
        """
        ...

    def save_turn_state(self, table_id: TableId, chair: Chair) -> None:
        """Write the chair's turn statement alone, with the account that sits there as the one that stated it: no
        version, no other column. The table's row is locked by this transaction, as it is for every write, so a move
        saved at the same moment is saved before or after it and keeps it.
        """
        ...

    def add_table(self, table: TableRecord, opener_name: str) -> None:
        """Insert the table with the opener's display name, which no later write changes."""
        ...

    def end_table(self, table_id: TableId, at: datetime, ending: Ending) -> None:
        """End the table whose row this transaction locked, once: its version rises by one, its dealer, last
        played time, opener's name and give-up request clear, and it keeps only its row and its create receipt, so its
        id is never issued again and a create retry finds it. Its book rows go with it. `ending` says why it ended;
        a receipt written after it stays.
        """
        ...

    def played_before(self, cutoff: datetime) -> tuple[TableId, ...]:
        """The live tables whose last deal or step of play was at or before `cutoff`, in id order; an unlocked read, so
        a candidate list.
        """
        ...

    def forget_ended_before(self, cutoff: datetime) -> int:
        """Forget what the tables that ended at or before `cutoff` keep: one with no game in the history is deleted
        with every receipt of it, so its id names no table, and the closer's name of the others is cleared. Nothing
        else changes, not even a version. Returns how many tables were deleted.
        """
        ...

    def empty_since(self, table_id: TableId) -> datetime | None:
        """Since when nobody has been at the table, or None while it is unset."""
        ...

    def paused_facts(self, table_id: TableId) -> PausedFacts:
        """The last played time and the opener's name of a live table."""
        ...

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        """Write the time since when nobody has been at the table, on the row this transaction locked; it changes
        nothing else, not even the version.
        """
        ...

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        """Every live table with whether a hand was dealt on it and its time since when nobody has been there, each
        row locked by this transaction.
        """
        ...

    def live_end_asks(self) -> tuple[LiveAsk, ...]:
        """Every live table whose current series holds a proposal to end it, or at its end the first „Neue Serie“, with
        the instant it was made: an unlocked read, since the server's start only arms timers that re-read each table
        under its row lock.
        """
        ...

    def add_receipt(self, receipt: Receipt) -> None: ...

    def store_leave(self, table_id: TableId, account_id: str, hold_seconds: float, *, newest_wins: bool) -> None:
        """Store the account's chair hold as due `hold_seconds` from now on the store's clock, in place of an earlier
        one when `newest_wins`, else only where the account has no hold at the table; nothing is stored unless the
        account holds a chair at the live table.
        """
        ...

    def delete_hold(self, table_id: TableId, account_id: str) -> None:
        """Drop the account's chair hold at the table, if any; a freeing that locked it makes this wait for its
        commit.
        """
        ...

    def locked_hold_due(self, table_id: TableId, account_id: str) -> bool:
        """Whether the account's chair hold at the table is due on the store's clock, its row locked by this
        transaction; False without a hold.
        """
        ...

    def due_holds(self, limit: int) -> tuple[HeldChair, ...]:
        """At most `limit` chair holds that are due on the store's clock, the earliest due first; no row is locked, so
        the list is a candidate list.
        """
        ...

    def hold_seconds_left(self, table_id: TableId) -> dict[str, int]:
        """The whole seconds, rounded up, each chair hold at the table has left on the store's clock, by account; a due
        hold has none left.
        """
        ...

    def tables_of(self, account_id: str) -> tuple[TableVersion, ...]:
        """The live tables the account holds a chair at, each with its version and turn statement times, in id order;
        no row is locked, so the list is a candidate list: a table may end or a chair move before the caller uses it,
        and a caller that shows more than the table ids reads each table again under its lock.
        """
        ...

    def open_table_ids(self) -> tuple[TableId, ...]:
        """The live tables listed to every member, in id order; no row is locked, so the list is a candidate list as
        `tables_of` is.
        """
        ...

    def versions_of(self, table_ids: Iterable[TableId]) -> tuple[TableVersion, ...]:
        """The version and turn statement times of each live table among `table_ids`, in id order; no row is locked."""
        ...

    def chairs_taken_by(self, table_ids: Iterable[TableId], account_ids: frozenset[str]) -> frozenset[OccupiedChair]:
        """The chairs at `table_ids` whose occupant is among `account_ids`; no row is locked."""
        ...


class TableTransactions(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def begin(self) -> AbstractContextManager[TableTransaction]:
        """One transaction: it commits when the block ends and rolls back when the block raises."""
        ...


def save_traced(
    transaction: TableTransaction,
    before: TableRecord,
    after: TableRecord,
    trace: str | None,
    *,
    played_at: datetime | None,
) -> None:
    """Save `after`, a change of `before` made in a request of `trace`, with the traces its version and acts are in."""
    transaction.save_table(replace(after, traces=traces_after(before, after, trace)), played_at=played_at)


@dataclass(frozen=True)
class LiveWait:
    table_id: TableId
    dealer: int | None
    empty_since: datetime | None


@dataclass(frozen=True)
class LiveAsk:
    table_id: TableId
    asked_at: datetime


@dataclass(frozen=True)
class PausedFacts:
    """What the store keeps beside a live table's record: the time of its last deal or step of play, None until the
    first deal, and the name its opener had when he opened it, None for a table opened before the name was kept.
    """

    last_played_at: datetime | None
    opener_name: str | None


@dataclass(frozen=True)
class OccupiedChair:
    table_id: TableId
    account_id: str


@dataclass(frozen=True)
class HeldChair:
    """A stored chair hold: the account whose chair at the table it holds."""

    table_id: TableId
    account_id: str


@dataclass(frozen=True)
class TableVersion:
    """A live table with the version it had at the read and the time of each turn statement of its chairs, in seat
    order: a statement leaves the version as it is and each chair keeps its own time, so a reader that asks cheaply
    whether the table changed asks both, and no chair's statement hides another's.
    """

    table_id: TableId
    version: int
    turn_statement_times: tuple[datetime, ...]
