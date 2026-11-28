"""A send-away: a person takes an agent's chair from it, at once and in every phase of a hand."""

from typing import TYPE_CHECKING, Final

from skat.table.member_place import at_the_table, book_after_send_away, may_send_away
from skat.table.records import Decision, Refusal, SendAway, TableId, TableRecord
from skat.table.rules import CommandIdReusedError, replayed_decision, seat_of, with_occupant

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.member_place import MemberBook
    from skat.table.records import Actor
    from skat.table.transactions import TableTransactions

SEND_AWAY_COMMAND: Final = "send-away"


def send_away_payload(command: SendAway) -> str:
    return f"{command.table_id}:{command.agent_account}"


def earlier_send_away(
    transactions: TableTransactions, actor: Actor, command_id: str, table_id: str, is_agent: Callable[[str], bool]
) -> Decision | None:
    """The outcome of the actor's earlier send-away under the command id, None if none; it writes nothing and raises
    `CommandIdReusedError` for another request under the id, which includes a send-away of an agent `is_agent` refuses.
    """
    with transactions.begin() as transaction:
        replay = transaction.replay(actor.account_id, command_id)
    if replay is None:
        return None
    agent = replay.payload.removeprefix(f"{table_id}:")
    if agent == replay.payload or not is_agent(agent):
        raise CommandIdReusedError
    return replayed_decision(replay, SEND_AWAY_COMMAND, send_away_payload(SendAway(command_id, table_id, agent)))


def decide_send_away(table: TableRecord, account_id: str) -> Decision:
    """The agent's chair is freed and keeps its number, whether or not a hand runs.

    The hand stays as it is and waits for a sitter; nothing is scored. The account must hold a chair here
    (`not-seated`) and be an agent (`not-an-agent`). Who may send an agent away is the caller's.
    """
    own = seat_of(table, account_id)
    if own is None or own.occupant is None:
        return Decision(table, Refusal.NOT_SEATED)
    if not own.occupant.is_agent:
        return Decision(table, Refusal.NOT_AN_AGENT)
    return Decision(with_occupant(table, own.seat, None))


def decide_send_away_by(
    table: TableRecord, command: SendAway, sender: Actor, connected_accounts: frozenset[str], is_member: bool
) -> Decision:
    """The send-away of the agent by the sender, if `may_send_away` lets the sender at the table (`at_the_table` of
    the open streams) and either a member of the calling group or the owner its chair stores for the agent. Anyone
    else is `not-allowed` and the table stays; the chair's own reasons are `decide_send_away`'s.
    """
    allowed = may_send_away(
        table,
        command.agent_account,
        viewer_account=sender.account_id,
        viewer_present=sender.account_id in at_the_table(table, connected_accounts),
        viewer_is_member=is_member,
    )
    return decide_send_away(table, command.agent_account) if allowed else Decision(table, Refusal.NOT_ALLOWED)


def save_book_after_send_away(book: MemberBook, table_id: TableId, agent_account: str) -> None:
    """Write the row `book_after_send_away` gives for the agent."""
    book.save_book_entry(book_after_send_away(book.locked_book_entry(table_id, agent_account), table_id, agent_account))
