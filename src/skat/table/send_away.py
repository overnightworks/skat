"""A send-away: a person takes an agent's chair from it, at once and in every phase of a hand."""

from typing import TYPE_CHECKING, Final

from skat.table.member_place import BookEntry, InviteRefusal, at_the_table, offer_of, seated_call_facts
from skat.table.records import Decision, Refusal, SendAway, TableId, TableRecord
from skat.table.rules import seat_of, with_occupant

if TYPE_CHECKING:
    from datetime import datetime

    from skat.table.member_place import MemberBook
    from skat.table.records import Actor

SEND_AWAY_COMMAND: Final = "send-away"


def send_away_payload(command: SendAway) -> str:
    return f"{command.table_id}:{command.agent_account}"


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
    table: TableRecord,
    command: SendAway,
    sender: Actor,
    connected_accounts: frozenset[str],
    is_member: bool,
    now: datetime,
) -> Decision:
    """The send-away of the agent by the sender, if `offer_of` lets the sender at the table (`at_the_table` of the
    open streams) and either a member of the calling group or the owner its chair stores for the agent. Anyone else
    is `not-allowed` and the table stays; the chair's own reasons are `decide_send_away`'s.
    """
    facts = seated_call_facts(
        command.agent_account,
        viewer_account=sender.account_id,
        viewer_present=sender.account_id in at_the_table(table, connected_accounts),
        viewer_is_member=is_member,
    )
    if offer_of(facts, table, None, now) in {InviteRefusal.NOT_PRESENT, InviteRefusal.NOT_A_MEMBER}:
        return Decision(table, Refusal.NOT_ALLOWED)
    return decide_send_away(table, command.agent_account)


def save_book_after_send_away(book: MemberBook, table_id: TableId, agent_account: str) -> None:
    """Write the agent's row once it was sent away: the epoch raised and any invitation to this table cleared, so an
    accept of an older epoch is stale and the standing no longer offers the place; a missing row counts as epoch 0.
    """
    entry = book.locked_book_entry(table_id, agent_account)
    book.save_book_entry(BookEntry(table_id, agent_account, (0 if entry is None else entry.epoch) + 1))
