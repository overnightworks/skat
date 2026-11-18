import asyncio
import threading
from typing import TYPE_CHECKING

from tandem import Hold, Roster

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import timedelta

    from tandem import Lapse


class HeldLease:
    """`kept`'s block: the holder is live from its entry to its exit, which no generator's shutdown can end early."""

    def __init__(self, leases: InMemoryLeases, holder: str) -> None:
        self._leases = leases
        self._holder = holder

    async def __aenter__(self) -> Hold:  # NOSONAR(S7503) tandem's `kept` is async
        if self._leases.starting_fails:
            raise self._leases.starting_fails.pop(0)
        self._leases.holders.append(self._holder)
        return Hold(generation="generation")

    async def __aexit__(self, *_exception: object) -> None:
        if self._leases.ending_gate is not None:
            await self._leases.ending_gate.wait()
        if self._leases.ending_fails:
            raise self._leases.ending_fails.pop(0)
        self._leases.holders.remove(self._holder)


class InMemoryLeases:
    """The stream leases of the pods that share this object, as tandem's `Leases` answers them: a holder is live from
    the entry of `kept` to its exit, and `live` lists them all. `settled` is what the roster answers.

    `serve_lapses` hands each of `lapses` to its handler, once more after a handler that raised, which it keeps in
    `handler_failures`, and sets `lapses_handed` when none is left.

    The failures to come are listed in `reading_fails`, `starting_fails`, `ending_fails` and `serving_fails`;
    `reading_hangs` never answers a read and `ending_gate` holds every ending until it is set. `read_threads` names
    the thread of each read and `read_started` is set by the first.
    """

    def __init__(self) -> None:
        self.holders: list[str] = []
        self.settled = True
        self.reading_fails: list[BaseException] = []
        self.reading_hangs = False
        self.ending_fails: list[BaseException] = []
        self.ending_gate: asyncio.Event | None = None
        self.starting_fails: list[BaseException] = []
        self.serving_fails: list[BaseException] = []
        self.read_threads: list[int] = []
        self.read_started = asyncio.Event()
        self.live_read_count = 0
        self.lapses: list[Lapse] = []
        self.handler_failures: list[Exception] = []
        self.lapses_handed = asyncio.Event()

    def kept(self, holder: str, *, every: timedelta) -> HeldLease:
        return HeldLease(self, holder)

    async def live(self) -> Roster:
        self.live_read_count += 1
        self.read_threads.append(threading.get_ident())
        self.read_started.set()
        if self.reading_hangs:
            await asyncio.Event().wait()
        if self.reading_fails:
            raise self.reading_fails.pop(0)
        return Roster(holders=frozenset(self.holders), settled=self.settled)

    async def serve_lapses(
        self,
        handle: Callable[[Lapse], Awaitable[None]],
        *,
        claimer: str,
        every: timedelta,
    ) -> None:
        if self.serving_fails:
            raise self.serving_fails.pop(0)
        while self.lapses:
            lapse = self.lapses.pop(0)
            try:
                await handle(lapse)
            except Exception as failure:
                self.lapses.append(lapse)
                self.handler_failures.append(failure)
        self.lapses_handed.set()
        await asyncio.Event().wait()
