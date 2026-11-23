"""A seated member's view of its table: what the member reads and when the members seated there are told it changed.

The view is the member's own `TableView` with the decision whether the table waits for it, both from one record, so
the seat check and the view cannot drift. `skat.web.member_place` builds the revision of a seat's view from
the table's version and the asks due. Its acts are the lines of the window beside the view, from the same record.
The record keeps the traces its version and its hand's steps and ending entered in; `traces_after` carries them over a
change, and `act_traces` and `traces_of_acts` map them to and from the acts' numbers.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.table.acts import Act, acts_of, next_seq_of, step_slot_of
from skat.table.awaiting import awaits_you
from skat.table.member_place import agents_seated_at
from skat.table.records import EntryTraces, TableId, TableRecord
from skat.table.rules import seat_of
from skat.table.views import TableView, view_of

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "MemberActs",
    "MemberView",
    "ViewSignal",
    "act_traces",
    "member_acts_of",
    "member_view_of",
    "traces_after",
    "traces_of_acts",
    "view_recipients",
]

ViewSignal = Callable[[TableId, frozenset[str]], None]
"""What a committed change tells: the table and the agents seated at it after the commit."""


@dataclass(frozen=True)
class MemberView:
    """The table as one seated account sees it, and whether the table waits for that account."""

    view: TableView
    awaits_you: bool
    traceparent: str | None
    """The trace of the request that moved the table to the view's version; None where none is stored."""


@dataclass(frozen=True)
class MemberActs:
    """The acts of the table's latest hand for the account that holds a chair, and the seat that is its own; `starts_at`
    is the number of the first act, or of the next one while none stands. `traces` are the traces the acts entered in by
    their numbers; an act that has none is not among them.
    """

    own_seat: int
    starts_at: int
    acts: tuple[Act, ...]
    traces: Mapping[int, str]


def member_view_of(table: TableRecord, account_id: str, present: frozenset[str], now: datetime) -> MemberView | None:
    """The view of the account that holds a chair at the table, `now` being the clock the chairs' statements are read
    on; None for an account that holds no chair.
    """
    if account_id not in {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}:
        return None
    view = view_of(table, account_id, present, now=now)
    return MemberView(view, awaits_you(view), table.traces.version)


def member_acts_of(table: TableRecord, account_id: str) -> MemberActs | None:
    """The acts of the account that holds a chair at the table; None for an account that holds no chair."""
    chair = seat_of(table, account_id)
    if chair is None:
        return None
    acts = acts_of(table, view_of(table, account_id, frozenset()))
    return MemberActs(chair.seat, acts[0].seq if acts else next_seq_of(table), acts, act_traces(table))


def _acts(table: TableRecord) -> tuple[Act, ...]:
    return acts_of(table, view_of(table, "", frozenset()))


def _trace_of(traces: EntryTraces, act: Act) -> str | None:
    slot = step_slot_of(act)
    return traces.ending if slot is None else dict(traces.steps).get(slot)


def _traces_by_act(version: str | None, traced: list[tuple[Act, str | None]]) -> EntryTraces:
    steps = tuple((slot, each) for act, each in traced if (slot := step_slot_of(act)) is not None and each is not None)
    ending = next((each for act, each in traced if step_slot_of(act) is None and each is not None), None)
    return EntryTraces(version, steps, ending)


def act_traces(table: TableRecord) -> dict[int, str]:
    """The trace of each act of the table's latest hand by the act's number; an act that has none is not among them."""
    return {act.seq: each for act in _acts(table) if (each := _trace_of(table.traces, act)) is not None}


def traces_of_acts(table: TableRecord, version: str | None, by_number: Mapping[int, str]) -> EntryTraces:
    """The traces of the table whose version entered in `version` and whose acts entered in `by_number`, the trace of
    each act by its number.
    """
    return _traces_by_act(version, [(act, by_number.get(act.seq)) for act in _acts(table)])


def traces_after(before: TableRecord, after: TableRecord, trace: str | None) -> EntryTraces:
    """The traces of `after`, a change of `before` made in a request of `trace`: the version has `trace` when the change
    raised it, and each act that `before` did not hold has it; what stood before keeps its trace, and a change made
    outside a trace adds none.
    """
    held = {act.seq: _trace_of(before.traces, act) for act in _acts(before)}
    traced = [(act, held.get(act.seq, trace)) for act in _acts(after)]
    return _traces_by_act(trace if after.version > before.version else before.traces.version, traced)


def view_recipients(before: TableRecord, after: TableRecord) -> frozenset[str]:
    """The agents a change of the table tells: those seated after it, when it raised the table's version."""
    return agents_seated_at(after) if after.version > before.version else frozenset()
