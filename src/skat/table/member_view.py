"""A seated member's view of its table: what the member reads and when the members seated there are told it changed.

The view is the member's own `TableView` with the decision whether the table waits for it, both from one record, so
the seat check and the view cannot drift. The revision a reader sees is the view's `version`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from skat.table.awaiting import awaits_you
from skat.table.member_place import agents_seated_at
from skat.table.records import TableId, TableRecord
from skat.table.views import TableView, view_of

__all__ = ["MemberView", "ViewSignal", "member_view_of", "view_recipients"]

ViewSignal = Callable[[TableId, frozenset[str]], None]
"""What a committed change tells: the table and the agents seated at it after the commit."""


@dataclass(frozen=True)
class MemberView:
    """The table as one seated account sees it, and whether the table waits for that account."""

    view: TableView
    awaits_you: bool


def member_view_of(table: TableRecord, account_id: str, present: frozenset[str]) -> MemberView | None:
    """The view of the account that holds a chair at the table; None for an account that holds none."""
    if account_id not in {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}:
        return None
    view = view_of(table, account_id, present)
    return MemberView(view, awaits_you(view))


def view_recipients(before: TableRecord, after: TableRecord) -> frozenset[str]:
    """The agents a change of the table tells: those seated after it, when it raised the table's version."""
    return agents_seated_at(after) if after.version > before.version else frozenset()
