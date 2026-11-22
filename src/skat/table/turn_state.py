"""What a chair's statement about its turns shows to the viewers of a table: the stopped outcome as stated, and while
the member thinks, the whole seconds the thinking has left under the cap.

The seconds are read from one clock, the service's, which also stamps each statement, so no viewer's clock decides,
and no timer runs on the server. Skat infers nothing about a turn from a member's silence. The cap lives here in the
core, not beside the web's constants, because the core computes the seconds and may not import the adapter.

The statement is stored, in the chair's own columns, because several pods serve a table and a restart must not lose
a value the runner believes stands; a chair already changes hands in one place, `with_occupant`, so the statement
goes with the seat and a new seat starts with none. Saving it leaves the table's version alone, because the version
also restarts the wait clock and the nudges and guards a member's asks.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from datetime import datetime

    from skat.table.records import TurnStatement

# A runner that died while it thought would leave its member thinking for ever; thinking shows no longer than this
# after the statement that began it.
THINKING_CAP_SECONDS: Final = 120


@dataclass(frozen=True)
class TurnStateView:
    """What a statement shows: the outcome its turns stopped with, or the seconds a running turn is shown for."""

    stopped: str | None
    thinking_seconds_left: int | None


def turn_state_view_of(statement: TurnStatement | None, now: datetime | None) -> TurnStateView | None:
    """The statement as the viewers see it; None when it shows nothing: no statement, one that says the turns answer, or
    thinking past its cap. Without `now`, thinking cannot be placed in time and shows nothing.
    """
    if statement is None:
        return None
    if statement.stopped is not None:
        return TurnStateView(statement.stopped, None)
    if not statement.thinking or now is None:
        return None
    elapsed = (now - statement.stated_at).total_seconds()
    left = min(THINKING_CAP_SECONDS, math.ceil(THINKING_CAP_SECONDS - elapsed))
    return TurnStateView(None, left) if left > 0 else None
