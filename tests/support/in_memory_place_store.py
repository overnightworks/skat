import asyncio
import time
from typing import TYPE_CHECKING

from agents.mcp_server.place_store import LapseRun, ListeningTurn, PlaceSignal, PlaceStoreError, Resubscribed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Collection
    from datetime import timedelta

    from agents.turn import Principal

# A resync that reads nothing fails its test instead of hanging it.
READ_WITHIN_SECONDS = 5


class InMemoryPlaceStore:
    """One pod's place store, as the Redis one answers it: what any call publishes reaches `received`, the listen
    record keeps each stream that honored a URI until its deadline on `clock`, and `lapse_due` turns a URI to no once
    a principal's last stream of it has lapsed. `inject` puts an event on `received` as another pod's would arrive.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._streams: dict[str, tuple[Principal, frozenset[str], float]] = {}
        self._inbox: asyncio.Queue[PlaceSignal | ListeningTurn | Resubscribed] | None = None
        self._listeners_read = asyncio.Event()
        self.unreachable = False

    def _queue(self) -> asyncio.Queue[PlaceSignal | ListeningTurn | Resubscribed]:
        if self._inbox is None:
            self._inbox = asyncio.Queue()
        return self._inbox

    def _reachable(self) -> None:
        if self.unreachable:
            raise PlaceStoreError("the store does not answer")

    async def inject(self, event: PlaceSignal | ListeningTurn | Resubscribed) -> None:
        """Puts the event on `received` and returns once the follower has handled it."""
        self._queue().put_nowait(event)
        await self.settled()

    async def settled(self) -> None:
        """Returns once the follower has handled everything put on `received` so far."""
        await self._queue().join()

    async def resubscribed(self) -> None:
        """The subscription is confirmed again, and returns once a read of `listeners` that it caused has answered."""
        self._listeners_read.clear()
        await self.inject(Resubscribed())
        async with asyncio.timeout(READ_WITHIN_SECONDS):
            await self._listeners_read.wait()

    async def publish(self, signal: PlaceSignal) -> None:
        self._reachable()
        self._queue().put_nowait(signal)

    async def received(self) -> AsyncIterator[PlaceSignal | ListeningTurn | Resubscribed]:
        # Each subscription starts on an empty inbox of the loop it runs on, as a restarted app's does.
        self._inbox = asyncio.Queue()
        yield Resubscribed()
        while True:
            event = await self._queue().get()
            yield event
            self._queue().task_done()

    async def acknowledged(
        self, stream: str, principal: Principal, uris: Collection[str], holds_for: timedelta
    ) -> frozenset[str]:
        self._reachable()
        if stream in self._streams:
            return frozenset()
        turned = frozenset(uri for uri in uris if uri not in self._honored_by(principal))
        self._streams[stream] = (principal, frozenset(uris), self._clock() + holds_for.total_seconds())
        for uri in turned:
            self._queue().put_nowait(ListeningTurn(principal, uri, listens=True))
        return turned

    async def ended(self, stream: str, holds_for: timedelta) -> None:
        self._reachable()
        if stream in self._streams:
            principal, uris, deadline = self._streams[stream]
            self._streams[stream] = (principal, uris, min(deadline, self._clock() + holds_for.total_seconds()))

    async def listens_to(self, principal: Principal, uri: str) -> bool:
        self._reachable()
        return uri in self._honored_by(principal)

    async def listeners(self, uri: str) -> frozenset[Principal]:
        try:
            self._reachable()
            return frozenset(
                principal for principal, uris, deadline in self._streams.values() if self._open(uri, uris, deadline)
            )
        finally:
            self._listeners_read.set()

    async def lapse_due(self, claimer: str) -> LapseRun:
        self._reachable()
        lapsed = {stream: held for stream, held in self._streams.items() if held[2] <= self._clock()}
        for stream in lapsed:
            del self._streams[stream]
        turns = tuple(
            ListeningTurn(principal, uri, listens=False)
            for principal, uris, _ in lapsed.values()
            for uri in uris - self._honored_by(principal)
        )
        for turn in turns:
            self._queue().put_nowait(turn)
        return LapseRun(turns=turns, stream_count=len(lapsed))

    def record_without_turn(
        self, stream: str, principal: Principal, uris: Collection[str], holds_for: timedelta
    ) -> None:
        """Another pod recorded the stream while this pod's subscription was down: no turn reaches `received`."""
        self._streams[stream] = (principal, frozenset(uris), self._clock() + holds_for.total_seconds())

    def _honored_by(self, principal: Principal) -> frozenset[str]:
        return frozenset(
            uri
            for held_by, uris, deadline in self._streams.values()
            if held_by == principal
            for uri in uris
            if deadline > self._clock()
        )

    def _open(self, uri: str, uris: frozenset[str], deadline: float) -> bool:
        return uri in uris and deadline > self._clock()
