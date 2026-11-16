import asyncio
from typing import TYPE_CHECKING

from logline import current_traceparent
from tandem import Resubscribed, Wake

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class LoopbackWakeChannel:
    """One pod's end of a `LoopbackWakeBus`: what any pod publishes reaches every pod's `received`, the publisher's
    own as well, as on Redis, each carrying the trace its publisher was in.
    """

    def __init__(self, bus: LoopbackWakeBus, *, acknowledging: bool) -> None:
        self._bus = bus
        self._acknowledging = acknowledging
        self.inbox: asyncio.Queue[Wake | Resubscribed | BaseException] = asyncio.Queue()
        self.failures_before_publishing: list[BaseException] = []
        self.turns_before_publishing = 0

    async def publish(self, address: str) -> None:
        for _ in range(self.turns_before_publishing):
            await asyncio.sleep(0)
        if self.failures_before_publishing:
            raise self.failures_before_publishing.pop(0)
        self._bus.published.append(address)
        for channel in self._bus.channels:
            channel.inbox.put_nowait(Wake(address, current_traceparent()))

    async def received(self) -> AsyncIterator[Wake | Resubscribed]:
        """Yields the acknowledgement of the subscription, unless the channel is one that never gets it, and then what
        arrives; an exception put in the inbox is raised.
        """
        if self._acknowledging:
            yield Resubscribed()
        while True:
            event = await self.inbox.get()
            if isinstance(event, BaseException):
                raise event
            yield event


class LoopbackWakeBus:
    """The pods of one test and every address published among them."""

    def __init__(self) -> None:
        self.channels: list[LoopbackWakeChannel] = []
        self.published: list[str] = []

    def pod(self, *, acknowledging: bool = True) -> LoopbackWakeChannel:
        channel = LoopbackWakeChannel(self, acknowledging=acknowledging)
        self.channels.append(channel)
        return channel


def single_pod_channel() -> LoopbackWakeChannel:
    """The channel of a deployment of one pod, for the tests that wire a whole app."""
    return LoopbackWakeBus().pod()
