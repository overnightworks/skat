from contextlib import ExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from skat.table.command_log import command_step, noted
from skat.table.records import Actor, Ending, Receipt, StopPlaying, TableId
from skat.table.rules import CommandIdReusedError, ends_unplayed
from skat.table.series_end import STOP_PLAYING_COMMAND, decide_stop_playing
from skat.table.server_steps import members_of
from skat.table.transactions import retried_on_duplicate_receipt
from skat.table.views import CommandResult, view_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from skat.table.records import Replay
    from skat.table.transactions import TableTransactions

__all__ = ["Stopped", "end_unplayed_table", "forget_ended_tables", "stop_playing", "unplayed_tables"]


@dataclass(frozen=True)
class Stopped:
    """What a stop did: the answer for the actor, and the agents whose standing the end changed, none for a refusal
    and a replay.
    """

    result: CommandResult
    members: frozenset[str]


def _replayed_stop(replay: Replay, actor: Actor, command: StopPlaying) -> CommandResult:
    """The ended table a stop already made; any other request under its key is refused."""
    if (replay.command, replay.payload) != (STOP_PLAYING_COMMAND, command.table_id):
        raise CommandIdReusedError
    return CommandResult(view_of(replay.table, actor.account_id, frozenset()))


def stop_playing(
    transactions: TableTransactions, actor: Actor, command: StopPlaying, now: Callable[[], datetime]
) -> Stopped | None:
    """End the table for everyone in one transaction under its row lock, or None when no live table has the id.

    A retry under the command id finds the receipt of the stop, which outlives the table, and answers the ended
    table. A refusal writes no receipt, so the id stays free.
    """
    with command_step(STOP_PLAYING_COMMAND, command.table_id) as step:
        stopped = retried_on_duplicate_receipt(lambda: _stop_once(transactions, actor, command, now))
        noted(step, None if stopped is None else stopped.result)
    return stopped


def _stop_once(
    transactions: TableTransactions, actor: Actor, command: StopPlaying, now: Callable[[], datetime]
) -> Stopped | None:
    identifier = TableId.parse(command.table_id)
    if identifier is None:
        return None
    with transactions.begin() as transaction:
        table = transaction.locked_table(identifier)
        replay = transaction.replay(actor.account_id, command.command_id)
        if replay is not None:
            return Stopped(_replayed_stop(replay, actor, command), frozenset())
        if table is None:
            return None
        refusal = decide_stop_playing(table, actor)
        if refusal is not None:
            return Stopped(CommandResult(view_of(table, actor.account_id, frozenset()), refusal), frozenset())
        members = members_of(transaction, table)
        transaction.end_table(identifier, now(), Ending.stopped())
        transaction.add_receipt(
            Receipt(actor.account_id, command.command_id, STOP_PLAYING_COMMAND, command.table_id, identifier)
        )
        ended = transaction.table(identifier)
    assert ended is not None  # noqa: S101 - narrows the type; the table this transaction ended is there as a tombstone
    return Stopped(CommandResult(view_of(ended, actor.account_id, frozenset())), members)


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


def forget_ended_tables(transactions: TableTransactions, days: int, now: datetime) -> int:
    """Forget what a table that ended `days` days ago or longer keeps, and return how many tables that deleted: see
    `TableTransaction.forget_ended_before`.
    """
    with transactions.begin() as transaction:
        return transaction.forget_ended_before(now - timedelta(days=days))
