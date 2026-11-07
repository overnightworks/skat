import copy
from contextlib import contextmanager
from typing import TYPE_CHECKING

from skat.table.records import Receipt, Replay
from skat.table.service import DuplicateReceiptError, TableService

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skat.table.records import TableId, TableRecord


class FakeTableStore:
    """The transaction port in memory: a block that raises leaves the store as it found it."""

    def __init__(self) -> None:
        self.tables: dict[str, TableRecord] = {}
        self.receipts: dict[tuple[str, str], Receipt] = {}
        self.fail_on_receipt: Exception | None = None

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
        return Replay(receipt.command, receipt.payload, self.tables[receipt.table_id.value])

    def table(self, table_id: TableId) -> TableRecord | None:
        return self.tables.get(table_id.value)

    def add_table(self, table: TableRecord) -> None:
        self.tables[table.id.value] = table

    def add_receipt(self, receipt: Receipt) -> None:
        if self.fail_on_receipt is not None:
            raise self.fail_on_receipt
        key = (receipt.account_id, receipt.command_id)
        if key in self.receipts:
            raise DuplicateReceiptError
        self.receipts[key] = receipt


def in_memory_tables() -> TableService:
    return TableService(FakeTableStore())
