import copy
from contextlib import contextmanager
from typing import TYPE_CHECKING

from skat.table.records import EndedTable, EndReason, Receipt, Replay, TableRecord
from skat.table.rules import CREATE_TABLE_COMMAND
from skat.table.service import TableService
from skat.table.transactions import DuplicateReceiptError, HeldTable, LiveWait, OccupiedChair, PausedFacts

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from skat.table.member_place import BookEntry
    from skat.table.records import TableId


class FreeChairReadyError(Exception):
    """The store's check refuses a free chair that is ready."""


class DealtWithoutTimeError(Exception):
    """The store's check refuses a dealt table that holds no last played time."""


class FakeTableStore:
    """The transaction port in memory: a block that raises leaves the store as it found it."""

    def __init__(self) -> None:
        self.tables: dict[str, TableRecord | EndedTable] = {}
        self.receipts: dict[tuple[str, str], Receipt] = {}
        self.ended_at: dict[str, datetime] = {}
        self.empty_since_by_table: dict[str, datetime | None] = {}
        self.last_played_at: dict[str, datetime] = {}
        self.opener_names: dict[str, str] = {}
        self.book: dict[tuple[str, str], BookEntry] = {}

    @contextmanager
    def begin(self) -> Iterator[FakeTableStore]:
        before = copy.deepcopy(
            (
                self.tables,
                self.receipts,
                self.ended_at,
                self.empty_since_by_table,
                self.last_played_at,
                self.opener_names,
                self.book,
            )
        )
        try:
            yield self
        except BaseException:
            (
                self.tables,
                self.receipts,
                self.ended_at,
                self.empty_since_by_table,
                self.last_played_at,
                self.opener_names,
                self.book,
            ) = before
            raise

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        receipt = self.receipts.get((account_id, command_id))
        if receipt is None:
            return None
        return Replay(
            receipt.command, receipt.payload, self.tables[receipt.table_id.value], receipt.refusal, receipt.holder
        )

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None:
        return self.tables.get(table_id.value)

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        table = self.table(table_id)
        return table if isinstance(table, TableRecord) else None

    def save_table(self, table: TableRecord, *, played_at: datetime | None) -> None:
        if any(chair.ready and chair.occupant is None for chair in table.chairs):
            message = f"table {table.id.value} would keep a free chair ready"
            raise FreeChairReadyError(message)
        if played_at is not None:
            self.last_played_at[table.id.value] = played_at
        if table.dealer is not None and table.id.value not in self.last_played_at:
            message = f"table {table.id.value} is dealt and holds no last played time"
            raise DealtWithoutTimeError(message)
        self.tables[table.id.value] = table

    def add_table(self, table: TableRecord, opener_name: str) -> None:
        self.tables[table.id.value] = table
        self.opener_names[table.id.value] = opener_name

    def end_table(self, table_id: TableId, at: datetime, empty_seconds: int) -> None:
        table = self.tables[table_id.value]
        self.tables[table_id.value] = EndedTable(table.id, table.version + 1, EndReason.EMPTY, empty_seconds)
        self.ended_at[table_id.value] = at
        self.last_played_at.pop(table_id.value, None)
        self.opener_names.pop(table_id.value, None)
        self.book = {key: entry for key, entry in self.book.items() if entry.table_id != table_id}
        self.receipts = {
            key: receipt
            for key, receipt in self.receipts.items()
            if receipt.table_id != table_id or receipt.command == CREATE_TABLE_COMMAND
        }

    def empty_since(self, table_id: TableId) -> datetime | None:
        return self.empty_since_by_table.get(table_id.value)

    def paused_facts(self, table_id: TableId) -> PausedFacts:
        return PausedFacts(self.last_played_at.get(table_id.value), self.opener_names.get(table_id.value))

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        self.empty_since_by_table[table_id.value] = since

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        return tuple(
            LiveWait(table.id, table.dealer, self.empty_since_by_table.get(table.id.value))
            for table in self.tables.values()
            if isinstance(table, TableRecord)
        )

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        return tuple(
            OccupiedChair(table.id, chair.occupant.account_id)
            for table in self.tables.values()
            if isinstance(table, TableRecord)
            for chair in table.chairs
            if chair.occupant is not None
        )

    def tables_of(self, account_id: str) -> tuple[HeldTable, ...]:
        return tuple(
            HeldTable(table.id, table.version)
            for table in sorted(self.tables.values(), key=lambda each: each.id.value)
            if isinstance(table, TableRecord)
            if any(chair.occupant is not None and chair.occupant.account_id == account_id for chair in table.chairs)
        )

    def locked_book_entry(self, table_id: TableId, agent_account: str) -> BookEntry | None:
        return self.book.get((table_id.value, agent_account))

    def locked_book_entries_of(self, agent_account: str) -> tuple[BookEntry, ...]:
        return tuple(entry for (_, account), entry in sorted(self.book.items()) if account == agent_account)

    def save_book_entry(self, entry: BookEntry) -> None:
        self.book[entry.table_id.value, entry.agent_account] = entry

    def book_accounts_at(self, table_id: TableId) -> frozenset[str]:
        return frozenset(account for (at_table, account) in self.book if at_table == table_id.value)

    def add_receipt(self, receipt: Receipt) -> None:
        key = (receipt.account_id, receipt.command_id)
        if key in self.receipts:
            raise DuplicateReceiptError
        self.receipts[key] = receipt


def in_memory_tables() -> TableService:
    return TableService(FakeTableStore())
