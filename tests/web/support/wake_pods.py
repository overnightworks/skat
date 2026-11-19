import asyncio
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from skat.web.wakes import SharedWakes, WakeList

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from skat.web.wakes import WakeChannel

# What a test waits for at most; a passing run takes a few event-loop turns.
ARRIVAL_SECONDS = 10


class RecordingChannel:
    """A pod's channel: records the addresses published through it and passes the rest on to the channel it wraps."""

    def __init__(self, channel: WakeChannel) -> None:
        self._channel = channel
        self.attempted: list[str] = []
        self.finished: list[str] = []

    async def publish(self, address: str) -> None:
        self.attempted.append(address)
        await self._channel.publish(address)
        self.finished.append(address)

    def __getattr__(self, name):
        return getattr(self._channel, name)


class Pod:
    """One pod of a test: its wake list, which publishes through the pod's channel, and the registrations it counts."""

    def __init__(self, channel: WakeChannel) -> None:
        self.channel = RecordingChannel(channel)
        self.ended = asyncio.Event()
        self.shared = SharedWakes(self.channel, end_process=self.ended.set)
        self.wake_list = WakeList(self.shared.publish)
        self.woken: dict[str, int] = {}
        self._arrived = asyncio.Event()

    def listen(self, name, *topics):
        def wake():
            self.woken[name] = self.woken.get(name, 0) + 1
            self._arrived.set()

        return self.wake_list.register(topics, wake)

    async def arrival_of(self, name, count=1):
        """Returns once `name` has been woken `count` times, or fails after a generous bound."""
        async with asyncio.timeout(ARRIVAL_SECONDS):
            while self.woken.get(name, 0) < count:
                self._arrived.clear()
                await self._arrived.wait()


def run_pods(channels: Sequence[WakeChannel], scenario: Callable[..., Awaitable[None]]) -> None:
    """Runs `scenario(*pods)`, one pod per channel, with every pod following its channel until the scenario ends."""

    async def run() -> None:
        pods = [Pod(channel) for channel in channels]
        async with AsyncExitStack() as stack:
            for pod in pods:
                await stack.enter_async_context(pod.shared.following(pod.wake_list))
            await scenario(*pods)

    asyncio.run(run())
