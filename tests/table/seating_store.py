from typing import TYPE_CHECKING

from skat.table.records import Replay
from tests.support.fake_tables import FakeTableStore

if TYPE_CHECKING:
    from skat.table.records import TableId, TableRecord


class SeatingTableStore(FakeTableStore):
    """The in-memory port with the seating commands' locking read, chair write and refusals in receipts."""

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        return self.table(table_id)

    def save_table(self, table: TableRecord) -> None:
        self.tables[table.id.value] = table

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        receipt = self.receipts.get((account_id, command_id))
        if receipt is None:
            return None
        return Replay(
            receipt.command, receipt.payload, self.tables[receipt.table_id.value], receipt.refusal, receipt.holder
        )
