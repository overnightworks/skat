from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import StrEnum


class StepOutcome[State](Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    @property
    def state(self) -> State: ...

    @property
    def refusal(self) -> StrEnum | None: ...


def replay_log[State, Step](
    start: State,
    steps: tuple[Step, ...],
    apply: Callable[[State, Step], StepOutcome[State]],
    log: str,
) -> State:
    """The state a stored log of steps leads to; a log the rules refuse is corrupt and raises."""
    state = start
    for place, step in enumerate(steps, start=1):
        outcome = apply(state, step)
        if outcome.refusal is not None:
            message = f"impossible {log} log: step {place} refused: {outcome.refusal.value}"
            raise ValueError(message)
        state = outcome.state
    return state
