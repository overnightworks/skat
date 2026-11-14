"""A seated member's view of its table: what the member reads and when the members seated there are told it changed.

The view is the member's own `TableView` with the decision whether the table waits for it, both from one record, so
the seat check and the view cannot drift. `skat.web.member_place` builds the revision of a seat's view from
the table's version and the asks due. Its acts are the lines of the window beside the view, from the same record.
"""

from collections.abc import Callable
from dataclasses import dataclass

from skat.table.acts import Act, acts_of, next_seq_of
from skat.table.awaiting import awaits_you
from skat.table.member_place import agents_seated_at
from skat.table.moment import TableMoment, moment_of
from skat.table.records import TableId, TableRecord
from skat.table.rules import seat_of
from skat.table.views import TableView, view_of

__all__ = [
    "MemberActs",
    "MemberView",
    "ViewSignal",
    "member_acts_of",
    "member_view_of",
    "moment_at",
    "moment_recipients",
    "view_recipients",
]

ViewSignal = Callable[[TableId, frozenset[str]], None]
"""What a committed change tells: the table and the agents seated at it after the commit."""


@dataclass(frozen=True)
class MemberView:
    """The table as one seated account sees it, and whether the table waits for that account."""

    view: TableView
    awaits_you: bool


@dataclass(frozen=True)
class MemberActs:
    """The acts of the table's latest hand for the account that holds a chair, and the seat that is its own; `starts_at`
    is the number of the first act, or of the next one while none stands.
    """

    own_seat: int
    starts_at: int
    acts: tuple[Act, ...]


def member_view_of(
    table: TableRecord, account_id: str, present: frozenset[str], opener_account: str | None
) -> MemberView | None:
    """The view of the account that holds a chair at the table, `opener_account` being the account that opened it;
    None for an account that holds no chair.
    """
    if account_id not in {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}:
        return None
    view = view_of(table, account_id, present, opener_account)
    return MemberView(view, awaits_you(view))


def member_acts_of(table: TableRecord, account_id: str) -> MemberActs | None:
    """The acts of the account that holds a chair at the table; None for an account that holds no chair."""
    chair = seat_of(table, account_id)
    if chair is None:
        return None
    acts = acts_of(table, view_of(table, account_id, frozenset()))
    return MemberActs(chair.seat, acts[0].seq if acts else next_seq_of(table), acts)


def view_recipients(before: TableRecord, after: TableRecord) -> frozenset[str]:
    """The agents a change of the table tells: those seated after it, when it raised the table's version."""
    return agents_seated_at(after) if after.version > before.version else frozenset()


def moment_at(table: TableRecord, account_id: str) -> TableMoment:
    """The moment of the account's seat at the live table; the moment does not depend on who is present."""
    return moment_of(view_of(table, account_id, frozenset()))


def moment_recipients(before: TableRecord, after: TableRecord) -> frozenset[str]:
    """The agents seated at both tables whose moment differs between them; an agent that sat down or stood up is told
    by the service, which tells its seat's change on its own.
    """
    return frozenset(
        account
        for account in agents_seated_at(before) & agents_seated_at(after)
        if moment_at(before, account) is not moment_at(after, account)
    )
