"""The minute a proposal to end the series, or at its end the first „Neue Serie“, waits for its answers, and the
timers that end it.
"""

import math
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from skat.web.presence_line import PresenceTimer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from skat.table.server_steps import EndAnswerLapse
    from skat.web.presence_line import TimerRuns


@dataclass(frozen=True)
class EndAnswers:
    """The step that ends what the minute of answers decides once it is over: a proposal to end the series, or at the
    series' end the table of a seat that stayed silent.

    `lapse(table_id)` answers the seconds the table's ask still has to wait, None once none stands, and whether the
    table ended, and raises when the store fails.
    """

    lapse: Callable[[str], Awaitable[EndAnswerLapse]]


class EndAnswerWatch:
    """The timers of the proposals to end a series and of the first „Neue Serie“, one waiting per table at most.

    `schedule(delay, action)` runs `action` once after `delay` seconds, `wake(table_id)` tells the table's streams that
    its view changed, `ended(table_id)` that the table ended, and `stopped()` says whether the presence has stopped,
    which starts no timer. A step the store
    refuses is asked again after `retry_seconds`.
    """

    def __init__(
        self,
        step: EndAnswers,
        clock: Callable[[], float],
        schedule: Callable[[float, Callable[[], Awaitable[None]]], None],
        runs: TimerRuns,
        wake: Callable[[str], None],
        ended: Callable[[str], None],
        stopped: Callable[[], bool],
        retry_seconds: float,
    ) -> None:
        self._step = step
        self._clock = clock
        self._schedule = schedule
        self._runs = runs
        self._wake = wake
        self._ended = ended
        self._stopped = stopped
        self._retry_seconds = retry_seconds
        self._dues: dict[str, float] = {}

    def watch(self, table_id: str, seconds_left: float) -> None:
        """Ask once `seconds_left` have passed whether the table's proposal to end the series has lapsed; the step
        re-reads the table, so a timer for a proposal that is gone, answered or replaced does nothing. A table with a
        timer waiting that falls due no later gets no second one, while a deadline found earlier than the waiting
        timer's, a later yes having timed a full minute, gets its own, so the minute the store holds is the minute kept.
        """
        due = self._clock() + seconds_left
        if self._stopped() or self._dues.get(table_id, math.inf) <= due:
            return
        self._dues[table_id] = due
        self._schedule(seconds_left, partial(self._lapse, table_id, due))

    def watch_all(self, seconds_left_by_table: Mapping[str, float]) -> None:
        """Start the minute of each live table's standing proposal found in the store, at the server's start and again
        while it serves, which recovers the proposals whose timer ran on a pod that is gone.
        """
        for table_id, seconds_left in seconds_left_by_table.items():
            self.watch(table_id, seconds_left)

    async def _lapse(self, table_id: str, due: float) -> None:
        if self._dues.get(table_id) == due:
            del self._dues[table_id]
        run = self._runs.start(PresenceTimer.END_ANSWER_LAPSE, table_id, table_id=table_id)
        try:
            left = await self._step.lapse(table_id)
        except Exception as failure:
            run.failed(failure)
            self.watch(table_id, self._retry_seconds)
            return
        run.succeeded()
        if left.table_stopped:
            self._ended(table_id)
        else:
            self._wake(table_id)
        if left.seconds_left is not None:
            self.watch(table_id, left.seconds_left)
