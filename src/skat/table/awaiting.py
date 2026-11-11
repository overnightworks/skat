"""Whether the table waits for the viewer's seat to act, decided from the viewer's own view so that the view and the
decision cannot disagree. A running hand waits for the seat on turn and, while a give-up is asked, for the opponent who
has not answered, unless a chair of the hand is open: then it waits for a sitter and for no seat. Between hands it
waits for each seat that has not continued, and for each that has not answered a proposal to end the series early.
"""

from skat.table.views import TableView, turn_seat_of

__all__ = ["awaits_you"]


def awaits_you(view: TableView) -> bool:
    """True when the viewer holds a chair and the table waits for its act."""
    own = next((chair for chair in view.chairs if chair.is_mine), None)
    if own is None:
        return False
    if view.hand is not None:
        if view.hand.waiting_seat is not None:
            return False
        return turn_seat_of(view.hand) == own.seat or _give_up_waits_for(view, own.seat)
    return (_a_result_or_series_end_stands(view) and not own.ready) or _proposal_waits_for(view, own.seat)


def _give_up_waits_for(view: TableView, seat: int) -> bool:
    asked = None if view.hand is None or view.hand.playing is None else view.hand.playing.give_up
    return asked is not None and seat not in (asked.asking_seat, asked.declined_seat)


def _a_result_or_series_end_stands(view: TableView) -> bool:
    return view.result is not None or (view.series is not None and view.series.over)


def _proposal_waits_for(view: TableView, seat: int) -> bool:
    proposal = None if view.series is None else view.series.end_proposal
    return proposal is not None and seat not in (proposal.proposer, proposal.accepter)
