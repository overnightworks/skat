from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from skat.engine.deal import SEATS
from skat.table.records import Decision, EndProposal, Refusal
from skat.table.rules import (
    bock_at_series_end,
    hand_runs,
    hand_was_dealt,
    new_series_ask_stands,
    seat_of,
    series_over,
)

if TYPE_CHECKING:
    from datetime import datetime

    from skat.table.records import Actor, Series, TableRecord

AGREE_TO_END_SERIES_COMMAND: Final = "agree-to-end-series"
REFUSE_TO_END_SERIES_COMMAND: Final = "refuse-to-end-series"
STOP_PLAYING_COMMAND: Final = "stop-playing"
END_ANSWER_SECONDS: Final = 60
"""How long a seat has to answer a proposal to end the series, and at the series' end the first „Neue Serie“; a seat
silent that long has said no.
"""


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
    A seat that already said yes changes nothing, and a yes that comes after the minute is over finds the proposal
    ended by the silent seats instead of adding to it.
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
    if answer_left(proposal.asked_at, now) <= timedelta(0):
        return decide_end_answer_lapse(table, now)
    if chair.seat in proposal.agreed:
        return Decision(table)
    agreed = proposal.agreed | {chair.seat}
    if agreed >= set(SEATS):
        return _ended_early(table, series)
    return _with_proposal(table, series, EndProposal(proposal.proposer, agreed, proposal.asked_at))


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
    """The time a standing proposal, or at the series' end the first „Neue Serie“, still waits for its answers; None
    while none stands.
    """
    asked_at = None if table.series is None else series_asked_at(table.series)
    return None if asked_at is None else answer_left(asked_at, now)


def series_asked_at(series: Series) -> datetime | None:
    """The instant the series' standing question was asked, a proposal to end it or at its end the first „Neue Serie“;
    None while none stands.
    """
    return series.end_proposal.asked_at if series.end_proposal is not None else series.new_series_asked_at


def decide_end_answer_lapse(table: TableRecord, now: datetime) -> Decision:
    """A proposal whose minute is over ends and names the seated seats that never said yes as its refusers, none when
    every silent chair is empty; any other table stays as it was.
    """
    series = table.series
    proposal = None if series is None else series.end_proposal
    if series is None or proposal is None or answer_left(proposal.asked_at, now) > timedelta(0):
        return Decision(table)
    seated = frozenset(chair.seat for chair in table.chairs if chair.occupant is not None)
    return _refused(table, series, seated - proposal.agreed)


def new_series_lapsed(table: TableRecord, now: datetime) -> bool:
    """At the series' end, whether the minute of „Neue Serie“ ran out: a seated seat never chose it, so the table
    ends. A minute with no silent seated chair left is no ask (`new_series_ask_stands`) and never lapses.
    """
    asked_at = None if table.series is None else table.series.new_series_asked_at
    return asked_at is not None and new_series_ask_stands(table) and answer_left(asked_at, now) <= timedelta(0)


def decide_stop_playing(table: TableRecord, actor: Actor) -> Refusal | None:
    """„Aufhören“ ends the table for everyone, from any seated person's chair, once the series is over: no chair, no
    series, a series not yet over.
    """
    if seat_of(table, actor.account_id) is None:
        return Refusal.NOT_SEATED
    if table.series is None:
        return Refusal.NO_SERIES
    return None if series_over(table) else Refusal.SERIES_NOT_OVER


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
