from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skat.table.records import Receipt, Replay, TableId, TableRecord
    from skat.table.service import TableTransaction, TableTransactions


class FaultyTableTransactions:
    """A transaction port that delegates to a real one and injects one fault through the port itself.

    `blind_first_replay` makes the first replay lookup find nothing, as when a rival request has not
    committed yet; `receipt_failure` is raised when a receipt is added.
    """

    def __init__(
        self,
        inner: TableTransactions,
        *,
        blind_first_replay: bool = False,
        receipt_failure: Exception | None = None,
    ) -> None:
        self._inner = inner
        self._blind_replays_left = 1 if blind_first_replay else 0
        self._receipt_failure = receipt_failure

    @contextmanager
    def begin(self) -> Iterator[_FaultyTransaction]:
        with self._inner.begin() as transaction:
            yield _FaultyTransaction(transaction, self)

    def take_blind_replay(self) -> bool:
        blind = self._blind_replays_left > 0
        self._blind_replays_left -= blind
        return blind

    @property
    def receipt_failure(self) -> Exception | None:
        return self._receipt_failure


class _FaultyTransaction:
    def __init__(self, inner: TableTransaction, faults: FaultyTableTransactions) -> None:
        self._inner = inner
        self._faults = faults

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        if self._faults.take_blind_replay():
            return None
        return self._inner.replay(account_id, command_id)

    def table(self, table_id: TableId) -> TableRecord | None:
        return self._inner.table(table_id)

    def add_table(self, table: TableRecord) -> None:
        self._inner.add_table(table)

    def add_receipt(self, receipt: Receipt) -> None:
        if self._faults.receipt_failure is not None:
            raise self._faults.receipt_failure
        self._inner.add_receipt(receipt)
