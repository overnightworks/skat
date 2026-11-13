from contextlib import ExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from skat.table.member_place import agents_seated_at
from skat.table.records import Actor, CloseTable, Ending, Receipt, Refusal, TableId, TableRecord
from skat.table.rules import CommandIdReusedError, ends_unplayed
from skat.table.views import CommandResult, view_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from skat.table.records import EndedTable, Replay
    from skat.table.transactions import TableTransaction, TableTransactions

__all__ = [
    "CLOSE_TABLE_COMMAND",
    "Closed",
    "close_table",
    "decide_close",
    "end_unplayed_table",
    "members_of",
    "table_with_opener",
    "unplayed_tables",
]

CLOSE_TABLE_COMMAND: Final = "close-table"


@dataclass(frozen=True)
class Closed:
    """What a close did: the answer for the actor, and the agents whose standing the end changed, none for a refusal
    and a replay.
    """

    result: CommandResult
    members: frozenset[str]


def decide_close(opener_account: str | None, actor: Actor) -> Refusal | None:
    """Only the account that opened the table closes it: a person who sits or watches, and a table whose opener is
    not known, are refused.
    """
    return None if opener_account == actor.account_id else Refusal.NOT_ALLOWED


def members_of(transaction: TableTransaction, table: TableRecord) -> frozenset[str]:
    """The agents whose standing the table's end changes: those that hold a chair and those invited."""
    return agents_seated_at(table) | transaction.book_accounts_at(table.id)


def _replayed_close(replay: Replay, actor: Actor, command: CloseTable) -> CommandResult:
    """The ended table a close already made; any other request under its key is refused."""
    if (replay.command, replay.payload) != (CLOSE_TABLE_COMMAND, command.table_id):
        raise CommandIdReusedError
    return CommandResult(view_of(replay.table, actor.account_id, frozenset()))


def close_table(
    transactions: TableTransactions, actor: Actor, command: CloseTable, now: Callable[[], datetime]
) -> Closed | None:
    """Close the table for everyone in one transaction under its row lock, or None when no live table has the id.

    A retry under the command id finds the receipt of the close, which outlives the table, and answers the ended
    table. A refusal writes no receipt, so the id stays free for the person who may close.
    """
    identifier = TableId.parse(command.table_id)
    if identifier is None:
        return None
    with transactions.begin() as transaction:
        table = transaction.locked_table(identifier)
        replay = transaction.replay(actor.account_id, command.command_id)
        if replay is not None:
            return Closed(_replayed_close(replay, actor, command), frozenset())
        if table is None:
            return None
        opener = transaction.opener_account(identifier)
        refusal = decide_close(opener, actor)
        if refusal is not None:
            return Closed(CommandResult(view_of(table, actor.account_id, frozenset(), opener), refusal), frozenset())
        members = members_of(transaction, table)
        transaction.end_table(identifier, now(), Ending.closed(actor.display_name))
        transaction.add_receipt(
            Receipt(actor.account_id, command.command_id, CLOSE_TABLE_COMMAND, command.table_id, identifier)
        )
        ended = transaction.table(identifier)
    assert ended is not None  # noqa: S101 - narrows the type; the table this transaction ended is there as a tombstone
    return Closed(CommandResult(view_of(ended, actor.account_id, frozenset())), members)


def table_with_opener(
    transactions: TableTransactions, table_id: str
) -> tuple[TableRecord | EndedTable | None, str | None]:
    """The table with the id and the account that opened it, an unlocked read; (None, None) for an id that names no
    table.
    """
    identifier = TableId.parse(table_id)
    if identifier is None:
        return None, None
    with transactions.begin() as transaction:
        return transaction.table(identifier), transaction.opener_account(identifier)


def unplayed_tables(transactions: TableTransactions, days: int, now: datetime) -> tuple[TableId, ...]:
    """The live tables that look due for `end_unplayed_table`, in id order: an unlocked read."""
    with transactions.begin() as transaction:
        return transaction.played_before(now - timedelta(days=days))


def end_unplayed_table(
    transactions: TableTransactions,
    table_id: TableId,
    days: int,
    writing: AbstractContextManager[frozenset[str] | None],
    now: Callable[[], datetime],
) -> frozenset[str] | None:
    """End a dealt table `days` days past its last deal or step of play, on the server's own account, and answer the
    agents whose standing that changed; None when it ended nothing. `writing` is entered once the row is locked and
    yields None once the presence has stopped.
    """
    with ExitStack() as after_commit, transactions.begin() as transaction:
        table, ended_at = transaction.locked_table(table_id), now()
        if table is None or after_commit.enter_context(writing) is None:
            return None
        if not ends_unplayed(table, transaction.paused_facts(table_id).last_played_at, ended_at, days):
            return None
        members = members_of(transaction, table)
        transaction.end_table(table_id, ended_at, Ending.unplayed(days))
    return members
