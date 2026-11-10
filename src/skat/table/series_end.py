from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.table.bock import bock_at_series_end
from skat.table.records import Decision, EndProposal, Refusal
from skat.table.rules import hand_runs, hand_was_dealt, seat_of, series_over

if TYPE_CHECKING:
    from skat.table.records import Actor, Series, TableRecord

AGREE_TO_END_SERIES_COMMAND: Final = "agree-to-end-series"
REFUSE_TO_END_SERIES_COMMAND: Final = "refuse-to-end-series"


@dataclass(frozen=True)
class SeriesEndCommand:
    """A yes or a no to ending the series between games; the chair comes from the session."""

    command_id: str
    table_id: str


def series_end_payload(command: SeriesEndCommand) -> str:
    """The receipt's payload: the table alone, because a proposal has no number a client could name."""
    return command.table_id


def decide_agree_to_end(table: TableRecord, actor: Actor) -> Decision:
    """Yes to ending the series: the first proposes, the second accepts and the third ends it at once; no chair, no
    series, a series already over, a running hand, then no game yet. A seat that already said yes changes nothing.
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
        return _with_proposal(table, series, EndProposal(chair.seat))
    if chair.seat in (proposal.proposer, proposal.accepter):
        return Decision(table)
    if proposal.accepter is None:
        return _with_proposal(table, series, EndProposal(proposal.proposer, chair.seat))
    return _ended_early(table, series)


def decide_refuse_to_end(table: TableRecord, actor: Actor) -> Decision:
    """No to ending the series: the proposal goes; no chair, then no proposal."""
    if seat_of(table, actor.account_id) is None:
        return Decision(table, Refusal.NOT_SEATED)
    if table.series is None or table.series.end_proposal is None:
        return Decision(table, Refusal.NO_PROPOSAL)
    return _with_proposal(table, table.series, None)


def _with_proposal(table: TableRecord, series: Series, proposal: EndProposal | None) -> Decision:
    return Decision(replace(table, version=table.version + 1, series=replace(series, end_proposal=proposal)))


def _ended_early(table: TableRecord, series: Series) -> Decision:
    """The series ends with the games so far and its pending Bock rounds; every „Weiter“ mark goes, since a mark set
    for the next hand would count as consent to „Neue Serie“.
    """
    chairs = tuple(replace(chair, ready=False) for chair in table.chairs)
    ended = replace(series, ended_early=True, end_proposal=None)
    return Decision(replace(table, version=table.version + 1, chairs=chairs, series=ended, bock=bock_at_series_end()))
