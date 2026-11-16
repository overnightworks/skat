"""A person at the table throws a reaction that every page at the table shows and plays: who may throw, and how often.

A reaction changes nothing stored and moves no table version. The closed set is `Reaction`: the emotes of the tray and
the table's objects a tap sets off. Anyone who sits at the table or watches it may throw; each person may throw
`REACTIONS_PER_WINDOW` within any `REACTION_WINDOW_SECONDS`, over all tables together. Time is passed in, so nothing
here reads a clock.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skat.table.views import TableView

__all__ = [
    "REACTIONS_PER_WINDOW",
    "REACTION_WINDOW_SECONDS",
    "Reaction",
    "ReactionRefusal",
    "reaction_refusal",
    "throwing_seat",
]

REACTIONS_PER_WINDOW: Final = 6
"""How many reactions one person may throw within `REACTION_WINDOW_SECONDS`."""

REACTION_WINDOW_SECONDS: Final = 10.0


class Reaction(StrEnum):
    """What a person may throw at the table; the value is the token clients read and send."""

    CLAP = "clap"
    LAUGH = "laugh"
    GASP = "gasp"
    FIRE = "fire"
    CHEERS = "cheers"
    KNOCK = "knock"
    COCKTAIL = "cocktail"
    SHELL = "shell"
    COASTER = "coaster"
    LAMP = "lamp"


class ReactionRefusal(StrEnum):
    """Why a reaction was refused; the value is the token clients read."""

    NOT_AT_THE_TABLE = "not-at-the-table"
    TOO_FAST = "too-fast"


def throwing_seat(view: TableView) -> int | None:
    """The viewer's own seat, None for a watcher."""
    return next((chair.seat for chair in view.chairs if chair.is_mine), None)


def reaction_refusal(
    view: TableView, *, watching: bool, thrown_at: Iterable[float], now: float
) -> ReactionRefusal | None:
    """Why the viewer of `view` may not throw now, None when it may. `watching` says whether the viewer has the table
    open, `thrown_at` is when the viewer threw before, at whichever table, and `now` the time of the request. A table
    that has ended is no table to be at.
    """
    if view.ended is not None or not (watching or throwing_seat(view) is not None):
        return ReactionRefusal.NOT_AT_THE_TABLE
    recent = sum(1 for moment in thrown_at if now - moment < REACTION_WINDOW_SECONDS)
    return ReactionRefusal.TOO_FAST if recent >= REACTIONS_PER_WINDOW else None
