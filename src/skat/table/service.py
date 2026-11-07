from typing import TYPE_CHECKING, Protocol

from skat.table.records import Actor, CreateTable, Receipt, Replay, TableId, TableRecord
from skat.table.rules import CommandIdReusedError, create_receipt, decide_create, replayed_table
from skat.table.views import TableView, view_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

__all__ = ["CommandIdReusedError", "DuplicateReceiptError", "TableService", "TableTransaction", "TableTransactions"]


class DuplicateReceiptError(Exception):
    """Another transaction stored a receipt under the same (account, command id) first."""


class TableTransaction(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def replay(self, account_id: str, command_id: str) -> Replay | None: ...

    def table(self, table_id: TableId) -> TableRecord | None: ...

    def add_table(self, table: TableRecord) -> None: ...

    def add_receipt(self, receipt: Receipt) -> None: ...


class TableTransactions(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def begin(self) -> AbstractContextManager[TableTransaction]:
        """One transaction: it commits when the block ends and rolls back when the block raises."""
        ...


class TableService:
    """The table commands and views; every command is one transaction."""

    def __init__(self, transactions: TableTransactions, new_table_id: Callable[[], TableId] = TableId.random) -> None:
        self._transactions = transactions
        self._new_table_id = new_table_id

    def create(self, actor: Actor, command: CreateTable) -> TableView:
        try:
            return self._create_once(actor, command)
        except DuplicateReceiptError:
            # An identical request committed between this one's lookup and its receipt; the retry finds that receipt.
            return self._create_once(actor, command)

    def _create_once(self, actor: Actor, command: CreateTable) -> TableView:
        with self._transactions.begin() as transaction:
            replay = transaction.replay(actor.account_id, command.command_id)
            if replay is not None:
                return view_of(replayed_table(replay), actor.account_id, frozenset())
            table = decide_create(actor, self._new_table_id())
            transaction.add_table(table)
            transaction.add_receipt(create_receipt(actor, command, table))
            return view_of(table, actor.account_id, frozenset())

    def view(self, actor: Actor, table_id: str, connected_accounts: frozenset[str]) -> TableView | None:
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            table = transaction.table(identifier)
        return None if table is None else view_of(table, actor.account_id, connected_accounts)
