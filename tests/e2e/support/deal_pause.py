import asyncio
import threading
from typing import TYPE_CHECKING

from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS, LoopScheduler

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class HeldDealPause:
    """The server's scheduler, which a test may keep from ending the pause before a table's next deal.

    While `hold` is on, the pause after a passed-in hand stays pending however long the test takes, so what the
    pages show during it does not depend on how fast a runner is. `release` lets every held pause end and the
    following ones run on the event loop's timers as usual. Every other timer always runs on those timers.
    """

    def __init__(self) -> None:
        self._timers = LoopScheduler()
        self._lock = threading.Lock()
        self._holding = False
        self._held: list[Callable[[], Awaitable[None]]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def hold(self) -> None:
        with self._lock:
            self._holding = True

    def release(self) -> None:
        with self._lock:
            self._holding = False
            held, self._held = self._held, []
            loop = self._loop
        for action in held:
            assert loop is not None
            loop.call_soon_threadsafe(self._timers.schedule, 0, action)

    def schedule(self, delay: float, action: Callable[[], Awaitable[None]]) -> None:
        with self._lock:
            if self._holding and delay == NEXT_DEAL_PAUSE_SECONDS:
                self._loop = asyncio.get_running_loop()
                self._held.append(action)
                return
        self._timers.schedule(delay, action)

    def cancel_all(self) -> None:
        with self._lock:
            self._held.clear()
        self._timers.cancel_all()
