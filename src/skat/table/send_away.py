"""A send-away: a person takes an agent's chair from it, at once and in every phase of a hand."""

from typing import Final

from skat.table.member_place import BookEntry
from skat.table.records import Decision, OccupantKind, Refusal, SendAway, TableId, TableRecord
from skat.table.rules import seat_of, with_occupant

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
    if own.occupant.kind is not OccupantKind.AGENT:
        return Decision(table, Refusal.NOT_AN_AGENT)
    return Decision(with_occupant(table, own.seat, None))


def book_after_send_away(entry: BookEntry | None, table_id: TableId, agent_account: str) -> BookEntry:
    """The agent's row once it was sent away: the epoch raised and any invitation to this table cleared, so an
    accept of an older epoch is stale and the standing no longer offers the place; a missing row counts as epoch 0.
    """
    return BookEntry(table_id, agent_account, (0 if entry is None else entry.epoch) + 1)
