"""What a chair's stated turn state is in the answers of a table and of the lobby, the same for every viewer."""

from typing import TYPE_CHECKING

from agents.turn import StopOutcome
from pydantic import BaseModel

if TYPE_CHECKING:
    from skat.table.turn_state import TurnStateView


class TurnStateAnswer(BaseModel):
    """What the occupant of a chair last stated about its turns: the outcome they stopped with, or, while a turn runs,
    the whole seconds the page keeps showing it, which the server counts from one clock under its cap. A chair with
    nothing to show has no such answer.
    """

    stopped: StopOutcome | None
    thinking_seconds_left: int | None


def turn_state_answer_of(view: TurnStateView | None) -> TurnStateAnswer | None:
    if view is None:
        return None
    return TurnStateAnswer(
        stopped=None if view.stopped is None else StopOutcome(view.stopped),
        thinking_seconds_left=view.thinking_seconds_left,
    )
