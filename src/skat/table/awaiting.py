"""Whether the table waits for the viewer's seat to act, decided from the viewer's own view so that the view and the
decision cannot disagree. A running hand waits for the seat on turn and, while a give-up is asked, for the opponent who
has not answered, and for each seat with a Kontra word open that it has not answered with no word, play never
waiting for it, unless a chair of the hand is open: then it waits for a sitter and for no seat. Between hands it
waits for each seat that has not continued, and for each that has not answered a proposal to end the series early.
"""

from enum import StrEnum

from skat.table.views import TableView, turn_seat_of

__all__ = ["WaitingCase", "awaits_you", "waiting_case"]


class WaitingCase(StrEnum):
    """Why the table waits for the viewer's seat; the value is the name clients read."""

    TURN = "turn"
    GIVE_UP = "give_up"
    KONTRA = "kontra"
    END_PROPOSAL = "end_proposal"
    RESULT = "result"
    SERIES_END = "series_end"


def awaits_you(view: TableView) -> bool:
    """True when the viewer holds a chair and the table waits for its act."""
    return waiting_case(view) is not None


def waiting_case(view: TableView) -> WaitingCase | None:
    """The first case that holds for the viewer's chair, in the order the cases are tested; None when none holds."""
    own = next((chair for chair in view.chairs if chair.is_mine), None)
    if own is None:
        return None
    if view.hand is not None:
        return None if view.hand.waiting_seat is not None else _case_in_the_hand(view, own.seat)
    return _case_between_hands(view, own.seat, own.ready)


def _case_in_the_hand(view: TableView, seat: int) -> WaitingCase | None:
    if turn_seat_of(view.hand) == seat:
        return WaitingCase.TURN
    if _give_up_waits_for(view, seat):
        return WaitingCase.GIVE_UP
    return WaitingCase.KONTRA if _kontra_word_waits(view) else None


def _case_between_hands(view: TableView, seat: int, ready: bool) -> WaitingCase | None:
    if _proposal_waits_for(view, seat):
        return WaitingCase.END_PROPOSAL
    if ready:
        return None
    if view.series is not None and view.series.over:
        return WaitingCase.SERIES_END
    return WaitingCase.RESULT if view.result is not None else None


def _give_up_waits_for(view: TableView, seat: int) -> bool:
    asked = None if view.hand is None or view.hand.playing is None else view.hand.playing.give_up
    return asked is not None and seat not in (asked.asking_seat, asked.declined_seat)


def _kontra_word_waits(view: TableView) -> bool:
    kontra = None if view.hand is None or view.hand.playing is None else view.hand.playing.kontra
    return kontra is not None and kontra.my_word is not None and not kontra.my_word_answered


def _proposal_waits_for(view: TableView, seat: int) -> bool:
    proposal = None if view.series is None else view.series.end_proposal
    return proposal is not None and seat not in (proposal.proposer, proposal.accepter)
