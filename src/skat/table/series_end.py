from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from skat.engine.deal import SEATS
from skat.table.records import Decision, EndProposal, Refusal
from skat.table.rules import bock_at_series_end, hand_runs, hand_was_dealt, seat_of, series_over

if TYPE_CHECKING:
    from datetime import datetime

    from skat.table.records import Actor, Series, TableRecord

AGREE_TO_END_SERIES_COMMAND: Final = "agree-to-end-series"
REFUSE_TO_END_SERIES_COMMAND: Final = "refuse-to-end-series"
END_ANSWER_SECONDS: Final = 60
"""How long a seat has to answer a proposal to end the series; a seat silent that long has said no."""


@dataclass(frozen=True)
class SeriesEndCommand:
    """A yes or a no to ending the series between games; the chair comes from the session."""

    command_id: str
    table_id: str


def series_end_payload(command: SeriesEndCommand) -> str:
    """The receipt's payload: the table alone, because a proposal has no number a client could name."""
    return command.table_id


def decide_agree_to_end(table: TableRecord, actor: Actor, now: datetime) -> Decision:
    """Yes to ending the series: the first yes proposes at `now`, and the series ends once every seat said yes; no
    chair, no series, a series already over, a running hand, no game yet, then a proposal refused since the last deal.
    A seat that already said yes changes nothing.
    """
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    series = table.series
    if series is None:
        return Decision(table, Refusal.NO_SERIES)
    if series_over(table):
        return Decision(table, Refusal.SERIES_OVER)
    if hand_runs(table):
        return Decision(table, Refusal.HAND_RUNNING)
    if not hand_was_dealt(table):
        return Decision(table, Refusal.NO_GAME_YET)
    proposal = series.end_proposal
    if proposal is None:
        if series.end_refused_by:
            return Decision(table, Refusal.END_REFUSED)
        return _with_proposal(table, series, EndProposal.by(chair.seat, now))
    if chair.seat in proposal.agreed:
        return Decision(table)
    agreed = proposal.agreed | {chair.seat}
    if agreed >= set(SEATS):
        return _ended_early(table, series)
    return _with_proposal(table, series, replace(proposal, agreed=agreed))


def decide_refuse_to_end(table: TableRecord, actor: Actor) -> Decision:
    """No to ending the series: the proposal ends and names the seat that refused until the next deal; no chair, then
    no proposal.
    """
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    if table.series is None or table.series.end_proposal is None:
        return Decision(table, Refusal.NO_PROPOSAL)
    return _refused(table, table.series, frozenset({chair.seat}))


def answer_left(asked_at: datetime, now: datetime) -> timedelta:
    """The time a question asked at `asked_at` still waits for its answers, negative once the minute is over."""
    return asked_at + timedelta(seconds=END_ANSWER_SECONDS) - now


def end_answer_left(table: TableRecord, now: datetime) -> timedelta | None:
    """The time a standing proposal still waits for its answers; None while no proposal stands."""
    proposal = None if table.series is None else table.series.end_proposal
    return None if proposal is None else answer_left(proposal.asked_at, now)


def decide_end_answer_lapse(table: TableRecord, now: datetime) -> Decision:
    """A proposal whose minute is over ends and names the seats that never said yes as its refusers; any other table
    stays as it was.
    """
    left = end_answer_left(table, now)
    if table.series is None or table.series.end_proposal is None or left is None or left > timedelta(0):
        return Decision(table)
    return _refused(table, table.series, frozenset(SEATS) - table.series.end_proposal.agreed)


def _refused(table: TableRecord, series: Series, refused_by: frozenset[int]) -> Decision:
    ended = replace(series, end_proposal=None, end_refused_by=refused_by)
    return Decision(replace(table, version=table.version + 1, series=ended))


def _with_proposal(table: TableRecord, series: Series, proposal: EndProposal) -> Decision:
    return Decision(replace(table, version=table.version + 1, series=replace(series, end_proposal=proposal)))


def _ended_early(table: TableRecord, series: Series) -> Decision:
    """The series ends with the games so far, its pending Bock rounds lapse; every „Weiter“ mark goes, since a mark set
    for the next hand would count as consent to „Neue Serie“.
    """
    chairs = tuple(replace(chair, ready=False) for chair in table.chairs)
    ended = replace(series, ended_early=True, end_proposal=None)
    return Decision(replace(table, version=table.version + 1, chairs=chairs, series=ended, bock=bock_at_series_end()))
