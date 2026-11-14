from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from skat.table.member_place import MemberBook

if TYPE_CHECKING:
    from collections.abc import Iterable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from skat.table.records import EndedTable, Ending, Receipt, Replay, TableId, TableRecord

__all__ = [
    "DuplicateReceiptError",
    "LiveWait",
    "OccupiedChair",
    "PausedFacts",
    "TableTransaction",
    "TableTransactions",
]


class DuplicateReceiptError(Exception):
    """Another transaction stored a receipt under the same (account, command id) first."""


class TableTransaction(MemberBook, Protocol):  # pragma: no cover - a port's method bodies are signatures
    def replay(self, account_id: str, command_id: str) -> Replay | None: ...

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None: ...

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        """A live table, its row locked exclusively for the transaction; only the commands that change it read this
        way. An ended table reads as none.
        """
        ...

    def save_table(self, table: TableRecord, *, played_at: datetime | None) -> None:
        """Write the table's version, chairs and dealer, a new hand's cards and steps, and new list entries.

        `played_at` is the time of the deal or step of play this save records and is written in the same statement
        as the dealer; None leaves the stored time as it is, so a save that deals a hand with none is refused.

        A passed-in hand's cards go and its steps stay until the next deal; a played-out hand, a record without a
        hand whose list grew, loses its cards and every step before its entry is appended. A stored hand stays as
        dealt: a record whose hand differs from it while the hand has progress raises, unless the third pass ended
        the hand of a table without Ramsch. A list that does not continue the stored one raises, unless the record is
        of a later series than the stored one: the stored rows of the earlier series stay and the table reads only
        its current series; a free chair that is ready raises too.
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

    def opener_account(self, table_id: TableId) -> str | None:
        """The account that opened the table, read from the create receipt that stays after its end; None when the
        table has none.
        """
        ...

    def played_before(self, cutoff: datetime) -> tuple[TableId, ...]:
        """The live tables whose last deal or step of play was at or before `cutoff`, in id order; an unlocked read, so
        a candidate list.
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

    def add_receipt(self, receipt: Receipt) -> None: ...

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]: ...

    def tables_of(self, account_id: str) -> tuple[TableVersion, ...]:
        """The live tables the account holds a chair at, each with its version, in id order; no row is locked, so the
        list is a candidate list: a table may end or a chair move before the caller uses it, and a caller that shows
        more than the table ids reads each table again under its lock.
        """
        ...

    def open_table_ids(self) -> tuple[TableId, ...]:
        """The live tables listed to every member, in id order; no row is locked, so the list is a candidate list as
        `tables_of` is.
        """
        ...

    def versions_of(self, table_ids: Iterable[TableId]) -> tuple[TableVersion, ...]:
        """The version of each live table among `table_ids`, in id order; no row is locked."""
        ...


class TableTransactions(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def begin(self) -> AbstractContextManager[TableTransaction]:
        """One transaction: it commits when the block ends and rolls back when the block raises."""
        ...


@dataclass(frozen=True)
class LiveWait:
    table_id: TableId
    dealer: int | None
    empty_since: datetime | None


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
class TableVersion:
    """A live table with the version it had at the read."""

    table_id: TableId
    version: int
