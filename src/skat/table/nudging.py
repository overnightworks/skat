"""A seated player's nudge asks a seat the table waits for once more: who may nudge which seat when, and the state of
each chair that each viewer is shown.

A nudge changes nothing stored and moves no table version. The nudges made at a version are kept by the web adapter
in memory beside the version's first sight, as `Nudges` per seat; time is the seconds the table has waited at the
version, so nothing here reads a clock. At most `NUDGES_PER_VERSION` nudges a seat per version, the first once the
table has waited `ASK_AGAIN_AFTER` and each next that long after the one before it.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.table.asking import ASK_AGAIN_AFTER
from skat.table.awaiting import awaited_seats

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skat.table.views import ChairView, TableView

__all__ = [
    "NUDGES_PER_VERSION",
    "NudgeRefusal",
    "NudgeRequest",
    "NudgeState",
    "Nudges",
    "is_retry",
    "nudge_refusal",
    "nudge_states",
    "own_nudges",
]

NUDGES_PER_VERSION: Final = 2
"""How many times at most a seat the table waits for is nudged at one version."""


class NudgeRefusal(StrEnum):
    """Why a nudge was refused; the value is the token clients read."""

    NOT_SEATED = "not-seated"
    STALE_VERSION = "stale-version"
    SEAT_OPEN = "seat-open"
    NOT_WAITING = "not-waiting"
    OWN_SEAT = "own-seat"
    AWAY = "away"
    TOO_EARLY = "too-early"
    ALREADY_NUDGED = "already-nudged"


@dataclass(frozen=True)
class NudgeRequest:
    """What a nudger sends: the version it read, the seat it nudges and how many nudges that seat had when it read."""

    version: int
    seat: int
    nudges: int


@dataclass(frozen=True)
class Nudges:
    """The nudges a seat has had at the current version: the seat of each nudger in the order made and how long the
    table had waited at the version when the latest was made.
    """

    nudgers: tuple[int, ...]
    waited: float

    @property
    def count(self) -> int:
        return len(self.nudgers)

    @property
    def by_seat(self) -> int:
        """The seat of the latest nudger."""
        return self.nudgers[-1]


@dataclass(frozen=True)
class NudgeState:
    """A chair's nudges for one viewer: how many, whether the viewer may nudge it now (the cap not reached; whether the
    minute has passed is not part of it) and the latest nudger's seat, only for the nudged seat's own viewer.
    """

    nudges: int
    may_nudge: bool
    by_seat: int | None


def _own_chair(view: TableView) -> ChairView | None:
    return next((chair for chair in view.chairs if chair.is_mine), None)


def _count_of(made: Nudges | None) -> int:
    return 0 if made is None else made.count


def _refusal_of_the_seat(view: TableView, request: NudgeRequest) -> NudgeRefusal | None:
    own = _own_chair(view)
    if own is None:
        return NudgeRefusal.NOT_SEATED
    if request.version != view.version:
        return NudgeRefusal.STALE_VERSION
    if request.seat == own.seat:
        return NudgeRefusal.OWN_SEAT
    if view.hand is not None and view.hand.waiting_seat is not None:
        return NudgeRefusal.SEAT_OPEN
    if request.seat not in awaited_seats(view):
        return NudgeRefusal.NOT_WAITING
    chair = next(chair for chair in view.chairs if chair.seat == request.seat)
    return NudgeRefusal.AWAY if chair.is_away else None


def is_retry(view: TableView, request: NudgeRequest, nudged: Mapping[int, Nudges]) -> bool:
    """True when the nudge that raised the count the request saw to the next one was made by the viewer's own chair."""
    own = _own_chair(view)
    made = nudged.get(request.seat)
    return (
        own is not None
        and made is not None
        and request.nudges < made.count
        and made.nudgers[request.nudges] == own.seat
    )


def nudge_refusal(
    view: TableView, request: NudgeRequest, waited: float, nudged: Mapping[int, Nudges]
) -> NudgeRefusal | None:
    """Why the viewer of `view` may not nudge as `request` says, None when it may; `waited` is the seconds the table
    has waited at the view's version and `nudged` the nudges made at it. A retry of a nudge made is no refusal; a
    request that did not see the seat's current count is refused and changes nothing.
    """
    refusal = _refusal_of_the_seat(view, request)
    if refusal is not None or is_retry(view, request, nudged):
        return refusal
    made = nudged.get(request.seat)
    if made is None:
        if waited < ASK_AGAIN_AFTER:
            return NudgeRefusal.TOO_EARLY
    elif made.count >= NUDGES_PER_VERSION or waited < made.waited + ASK_AGAIN_AFTER:
        return NudgeRefusal.ALREADY_NUDGED
    return None if request.nudges == _count_of(made) else NudgeRefusal.ALREADY_NUDGED


def nudge_states(view: TableView, nudged: Mapping[int, Nudges]) -> dict[int, NudgeState]:
    """The state of each chair the table waits for that is not away, for the viewer of `view`: a seated viewer who is
    not that chair's occupant may nudge it; the chair's own viewer and a watcher see it once it was nudged. Nothing
    while a chair of the hand is open.
    """
    if view.hand is not None and view.hand.waiting_seat is not None:
        return {}
    seated = _own_chair(view) is not None
    awaited = awaited_seats(view)
    states = {
        chair.seat: _state_of_chair(chair, nudged.get(chair.seat), seated=seated)
        for chair in view.chairs
        if chair.seat in awaited and not chair.is_away
    }
    return {seat: state for seat, state in states.items() if state is not None}


def _state_of_chair(chair: ChairView, made: Nudges | None, *, seated: bool) -> NudgeState | None:
    count = _count_of(made)
    if chair.is_mine:
        return None if made is None else NudgeState(count, may_nudge=False, by_seat=made.by_seat)
    if not seated:
        return None if made is None else NudgeState(count, may_nudge=False, by_seat=None)
    return NudgeState(count, may_nudge=count < NUDGES_PER_VERSION, by_seat=None)


def own_nudges(view: TableView, states: Mapping[int, NudgeState]) -> int:
    """The nudges the viewer's own chair has had, which its agent's revision adds."""
    own = _own_chair(view)
    state = None if own is None else states.get(own.seat)
    return 0 if state is None else state.nudges
