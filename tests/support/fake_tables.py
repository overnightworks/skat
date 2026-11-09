import copy
from contextlib import contextmanager
from typing import TYPE_CHECKING

from skat.table.records import Receipt, Replay
from skat.table.service import DuplicateReceiptError, OccupiedChair, TableService

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skat.table.records import TableId, TableRecord


class FreeChairReadyError(Exception):
    """The store's check refuses a free chair that is ready."""


class FakeTableStore:
    """The transaction port in memory: a block that raises leaves the store as it found it."""

    def __init__(self) -> None:
        self.tables: dict[str, TableRecord] = {}
        self.receipts: dict[tuple[str, str], Receipt] = {}

    @contextmanager
    def begin(self) -> Iterator[FakeTableStore]:
        before = copy.deepcopy((self.tables, self.receipts))
        try:
            yield self
        except BaseException:
            self.tables, self.receipts = before
            raise

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        receipt = self.receipts.get((account_id, command_id))
        if receipt is None:
            return None
        return Replay(
            receipt.command, receipt.payload, self.tables[receipt.table_id.value], receipt.refusal, receipt.holder
        )

    def table(self, table_id: TableId) -> TableRecord | None:
        return self.tables.get(table_id.value)

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        return self.table(table_id)

    def save_table(self, table: TableRecord) -> None:
        if any(chair.ready and chair.occupant is None for chair in table.chairs):
            message = f"table {table.id.value} would keep a free chair ready"
            raise FreeChairReadyError(message)
        self.tables[table.id.value] = table

    def add_table(self, table: TableRecord) -> None:
        self.tables[table.id.value] = table

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        return tuple(
            OccupiedChair(table.id, chair.occupant.account_id)
            for table in self.tables.values()
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
