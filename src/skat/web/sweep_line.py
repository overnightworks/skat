"""The log line of the hourly table sweep: one `table_sweep.ended` for a run that did work, for the first run of a
streak that failed and for the run that ends the streak, and none for a run that found nothing to do.
"""

import logging
from dataclasses import asdict, dataclass
from enum import StrEnum

from logline import StepTimer

_LOGGER = logging.getLogger(__name__)


class SweepFailure(StrEnum):
    """Why a run of the sweep failed: the one set of `reason`s of its log line."""

    STEP_FAILED = "step_failed"


@dataclass(frozen=True)
class SweepCounts:
    """What one run did: the tables it ended and forgot and the sessions it forgot."""

    ended_table_count: int = 0
    forgotten_table_count: int = 0
    forgotten_session_count: int = 0

    def did_work(self) -> bool:
        return any(asdict(self).values())


class SweepLine:
    """Writes the lines of the runs of one sweep, and counts the runs that failed one after the other."""

    def __init__(self) -> None:
        self._failed_run_count = 0

    def run(self) -> StepTimer:
        """The timer of a run, which starts now; `written` ends it or leaves it unwritten."""
        return StepTimer("table_sweep.ended", _LOGGER)

    def written(self, step: StepTimer, counts: SweepCounts, *, failed: bool) -> None:
        """A failed run writes its line only when it is the first of its streak, as a warning; the run after a streak
        writes its line with the streak's length, whatever it did.
        """
        step.add(**asdict(counts))
        if failed:
            self._failed_run_count += 1
            if self._failed_run_count == 1:
                step.add(failed_run_count=1)
                step.fail(SweepFailure.STEP_FAILED)
                step.handled()
                step.end()
            return
        if self._failed_run_count or counts.did_work():
            step.add(failed_run_count=self._failed_run_count)
            step.end()
        self._failed_run_count = 0
