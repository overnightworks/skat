"""A seat the table waits for is asked again after a pause: how many asks are due after a wait, and the revision of
a seat's view that carries them.

The revision is the table's version times a fixed base plus the count of asks. The table's version never moves for an
ask, so a command's version guard and a person's stream are as before. The base is larger than the cap on asks, so the
revisions of two versions never meet.
"""

from typing import Final

__all__ = ["ASKS_AGAIN", "ASK_AGAIN_AFTER", "ASK_SLOTS", "asks_due", "revision_of"]

ASK_AGAIN_AFTER: Final = 60.0
"""Seconds the table waits for a seat at one version before the seat is asked once more."""

ASKS_AGAIN: Final = 2
"""How many times at most a seat is asked again at one version."""

ASK_SLOTS: Final = 16
"""The revisions one version owns: the asks and room for more."""


def asks_due(waiting_since: float, now: float) -> int:
    """The asks due for a seat the table has waited for since `waiting_since`, both on one monotonic clock."""
    return min(ASKS_AGAIN, max(0, int((now - waiting_since) // ASK_AGAIN_AFTER)))


def revision_of(version: int, asks: int) -> int:
    """The revision of a seat's view at the table's `version` after `asks` asks."""
    return version * ASK_SLOTS + asks
