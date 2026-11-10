import copy
from contextlib import contextmanager
from typing import TYPE_CHECKING

from skat.table.records import EndedTable, EndReason, Receipt, Replay, TableRecord
from skat.table.rules import CREATE_TABLE_COMMAND
from skat.table.service import DuplicateReceiptError, LiveWait, OccupiedChair, TableService

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from skat.table.records import TableId


class FreeChairReadyError(Exception):
    """The store's check refuses a free chair that is ready."""


class FakeTableStore:
    """The transaction port in memory: a block that raises leaves the store as it found it."""

    def __init__(self) -> None:
        self.tables: dict[str, TableRecord | EndedTable] = {}
        self.receipts: dict[tuple[str, str], Receipt] = {}
        self.ended_at: dict[str, datetime] = {}
        self.empty_since_by_table: dict[str, datetime | None] = {}

    @contextmanager
    def begin(self) -> Iterator[FakeTableStore]:
        before = copy.deepcopy((self.tables, self.receipts, self.ended_at, self.empty_since_by_table))
        try:
            yield self
        except BaseException:
            self.tables, self.receipts, self.ended_at, self.empty_since_by_table = before
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

    def save_table(self, table: TableRecord) -> None:
        if any(chair.ready and chair.occupant is None for chair in table.chairs):
            message = f"table {table.id.value} would keep a free chair ready"
            raise FreeChairReadyError(message)
        self.tables[table.id.value] = table

    def add_table(self, table: TableRecord) -> None:
        self.tables[table.id.value] = table

    def end_table(self, table_id: TableId, at: datetime, empty_seconds: int) -> None:
        table = self.tables[table_id.value]
        self.tables[table_id.value] = EndedTable(table.id, table.version + 1, EndReason.EMPTY, empty_seconds)
        self.ended_at[table_id.value] = at
        self.receipts = {
            key: receipt
            for key, receipt in self.receipts.items()
            if receipt.table_id != table_id or receipt.command == CREATE_TABLE_COMMAND
        }

    def empty_since(self, table_id: TableId) -> datetime | None:
        return self.empty_since_by_table.get(table_id.value)

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

    def add_receipt(self, receipt: Receipt) -> None:
        key = (receipt.account_id, receipt.command_id)
        if key in self.receipts:
            raise DuplicateReceiptError
        self.receipts[key] = receipt


def in_memory_tables() -> TableService:
    return TableService(FakeTableStore())
