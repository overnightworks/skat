"""The log line of a background run: one line for a run that did work, for the first run of a streak that failed and for
the run that ends the streak, and none for a run that found nothing to do.
"""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from logline import StepTimer

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)


class RunFailure(StrEnum):
    """Why a run failed: the one set of `reason`s of a run's log line."""

    STEP_FAILED = "step_failed"


class RunLine:
    """Writes the lines of the runs of one background job, and counts the runs that failed one after the other."""

    def __init__(self, event: str) -> None:
        self._event = event
        self.failed_run_count = 0

    def run(self) -> StepTimer:
        """The timer of a run, which starts now; `written` ends it or leaves it unwritten."""
        return StepTimer(self._event, _LOGGER)

    def written(self, step: StepTimer, counts: Mapping[str, int], *, failed: bool) -> None:
        """A failed run writes its line only when it is the first of its streak, as a warning; the run after a streak
        writes its line with the streak's length, whatever it did.
        """
        step.add(**counts)
        if failed:
            self.failed_run_count += 1
            if self.failed_run_count == 1:
                step.add(failed_run_count=1)
                step.fail(RunFailure.STEP_FAILED)
                step.handled()
                step.end()
            return
        if self.failed_run_count or any(counts.values()):
            step.add(failed_run_count=self.failed_run_count)
            step.end()
        self.failed_run_count = 0
