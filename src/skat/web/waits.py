"""How long the table has waited at its version, and the nudges made at it, kept in this process only.

`Presence` owns the one `AskClock`. Every answer of a table notes the table's version in it, so a wait starts at the
first read after a commit, which is the committing command's own answer, whoever reads. Only the event loop's thread
touches it. A restart starts every wait afresh and forgets every nudge.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from skat.table.nudging import Nudges, NudgeState, nudge_states

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

    from skat.table.views import TableView

__all__ = ["AskClock"]


@dataclass
class _Wait:
    version: int
    since: float
    pulsed: set[str] = field(default_factory=set[str])
    nudged: dict[int, Nudges] = field(default_factory=dict[int, Nudges])


class AskClock:
    """When each table began to wait at its latest version, for whom its pulses are scheduled, and the nudges made at
    that version.

    Only a higher version replaces a table's entry; a version already seen keeps the earliest time, and a lower one,
    read by a transaction that began before a newer commit, changes nothing and has no wait. A table that ends while
    one of its views is being read gets no entry from that read, so an entry never outlives its table.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._waits: dict[str, _Wait] = {}
        self._reading: dict[str, int] = {}
        self._ended_while_reading: set[str] = set()

    def now(self) -> float:
        return self._clock()

    @contextmanager
    def reading(self, table_id: str) -> Generator[None]:
        """Around the read of a table's view, from before the store is read until the version is seen."""
        self._reading[table_id] = self._reading.get(table_id, 0) + 1
        try:
            yield
        finally:
            self._reading[table_id] -= 1
            if not self._reading[table_id]:
                del self._reading[table_id]
                self._ended_while_reading.discard(table_id)

    def see(self, table_id: str, version: int) -> float | None:
        """Since when the table has been at `version`, noting it first; None when the entry holds a higher one or
        the table ended while it was being read.
        """
        if table_id in self._ended_while_reading:
            return None
        wait = self._waits.get(table_id)
        if wait is None or version > wait.version:
            wait = self._waits[table_id] = _Wait(version, self._clock())
        return wait.since if wait.version == version else None

    def claim_pulses(self, table_id: str, version: int, account_id: str) -> bool:
        """True once for an account at the entry's version: the caller schedules its pulses."""
        wait = self._waits.get(table_id)
        if wait is None or wait.version != version or account_id in wait.pulsed:
            return False
        wait.pulsed.add(account_id)
        return True

    def is_current(self, table_id: str, version: int) -> bool:
        wait = self._waits.get(table_id)
        return wait is not None and wait.version == version

    def standing(self, view: TableView) -> tuple[float, Mapping[int, Nudges]] | None:
        """How long the table has waited at the view's version and the nudges made at it, noting the version; None
        for an ended table and for a view older than the entry.
        """
        if view.ended is not None:
            return None
        since = self.see(view.id, view.version)
        if since is None:
            return None
        return self._clock() - since, self._waits[view.id].nudged

    def nudges_of(self, view: TableView) -> Mapping[int, NudgeState]:
        """The nudge state of each chair for the viewer of `view`; none for an ended table and a view older than the
        entry.
        """
        standing = self.standing(view)
        return {} if standing is None else nudge_states(view, standing[1])

    def nudge(self, table_id: str, seat: int, by_seat: int, waited: float) -> None:
        """Records a nudge of `seat` made `waited` seconds into the entry's version, which the caller has just read
        the standing of on the event loop's thread.
        """
        nudged = self._waits[table_id].nudged
        previous = nudged.get(seat)
        earlier = () if previous is None else previous.nudgers
        nudged[seat] = Nudges(nudgers=(*earlier, by_seat), waited=waited)

    def drop(self, table_id: str) -> None:
        self._waits.pop(table_id, None)
        if table_id in self._reading:
            self._ended_while_reading.add(table_id)
