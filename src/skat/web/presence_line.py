"""The log lines of presence's timers: a timer's run is one try of its action for one table or one member, and the
runs of one timer for one subject that fail one after the other are a streak, written as `run_line` writes it.
"""

from enum import StrEnum
from typing import TYPE_CHECKING

from skat.web.run_line import RunLine

if TYPE_CHECKING:
    from collections.abc import Callable

    from logline import StepTimer

EVENT = "presence_timer.ended"


class PresenceTimer(StrEnum):
    """The timers of the presence: the `timer` of their log line."""

    LEASE_SETTLE = "lease_settle"
    NEXT_DEAL = "next_deal"
    EMPTY_SINCE_WRITE = "empty_since_write"
    EMPTY_TABLE_END = "empty_table_end"
    CHAIR_RELEASE = "chair_release"
    CLOSE_ABSENCE_CHECK = "close_absence_check"


class TimerRun:
    """One try of a timer's action, which starts when it is made and ends with `succeeded` or `failed`."""

    def __init__(self, line: RunLine, step: StepTimer, settled: Callable[[], None]) -> None:
        self._line = line
        self._step = step
        self._settled = settled

    def succeeded(self) -> None:
        self._written(failed=False)

    def failed(self) -> None:
        self._written(failed=True)

    def _written(self, *, failed: bool) -> None:
        self._line.written(self._step, {}, failed=failed)
        self._settled()


class TimerRuns:
    """The streaks of the presence's timers, one per timer and subject (a table, or a table and a member)."""

    def __init__(self) -> None:
        self._lines: dict[tuple[str, ...], RunLine] = {}

    def start(self, timer: PresenceTimer, *subject: str, table_id: str | None = None) -> TimerRun:
        """A run of `timer` for the subject. The line names the table and never a member, whose id a failure's own
        message may carry.
        """
        key = (timer, *subject)
        line = self._lines.setdefault(key, RunLine(EVENT))
        step = line.run()
        step.add(timer=timer)
        if table_id is not None:
            step.add(table_id=table_id)
        return TimerRun(line, step, lambda: self._forget_unless_failing(key, line))

    def _forget_unless_failing(self, key: tuple[str, ...], line: RunLine) -> None:
        if not line.failed_run_count:
            self._lines.pop(key, None)
