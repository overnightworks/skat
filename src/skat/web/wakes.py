import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

import structlog
from tandem import Resubscribed, StoreError, Wake

from skat.web.secret_files import StartRefusedError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterable

# How long a pod waits at its start for its first subscription to the channel, so that a wrong URL fails loud instead
# of hanging; the platform's liveness window is longer.
STARTUP_SECONDS: Final = 10
_PUBLISH_ATTEMPTS: Final = 2

log = structlog.get_logger()


@dataclass(frozen=True)
class TableTopic:
    """What a wake is about: one table."""

    table_id: str


@dataclass(frozen=True)
class AccountTopic:
    """What a wake is about: one account, whichever tables it holds."""

    account_id: str


@dataclass(frozen=True)
class OpenTablesTopic:
    """What a wake is about: the set of open tables, which a table opened joins."""


Topic = TableTopic | AccountTopic | OpenTablesTopic


@dataclass(frozen=True, eq=False)
class Registration:
    """One stream's wake and the topics it listens to."""

    topics: frozenset[Topic]
    wake: Callable[[], None]


_TABLE_PREFIX: Final = "table:"
_ACCOUNT_PREFIX: Final = "account:"
_OPEN_TABLES_ADDRESS: Final = "open-tables"


def _address_of(topic: Topic) -> str:
    """What a wake names on the channel between pods: the topic and never any content."""
    if isinstance(topic, TableTopic):
        return _TABLE_PREFIX + topic.table_id
    if isinstance(topic, AccountTopic):
        return _ACCOUNT_PREFIX + topic.account_id
    return _OPEN_TABLES_ADDRESS


def _topic_of(address: str) -> Topic | None:
    if address == _OPEN_TABLES_ADDRESS:
        return OpenTablesTopic()
    if address.startswith(_TABLE_PREFIX):
        return TableTopic(address.removeprefix(_TABLE_PREFIX))
    if address.startswith(_ACCOUNT_PREFIX):
        return AccountTopic(address.removeprefix(_ACCOUNT_PREFIX))
    return None


class WakeList:
    """Which wakes listen to which topic. A wake carries no data: the woken stream reads its own state again.

    A change committed here is `wake`d, which tells the other pods through `publish` as well; `wake_locally` is for a
    wake that came from another pod and so is told no further. Used on the event loop's thread only, so it takes no
    lock.
    """

    def __init__(self, publish: Callable[[Topic], None]) -> None:
        self._registrations: dict[Topic, list[Registration]] = {}
        self._publish = publish

    def register(self, topics: Iterable[Topic], wake: Callable[[], None]) -> Registration:
        registration = Registration(frozenset(topics), wake)
        for topic in registration.topics:
            self._registrations.setdefault(topic, []).append(registration)
        return registration

    def unregister(self, registration: Registration) -> None:
        for topic in registration.topics:
            listening = self._registrations[topic]
            listening.remove(registration)
            if not listening:
                del self._registrations[topic]

    def wake(self, topic: Topic, sparing: Registration | None = None) -> None:
        """Wake every registration of the topic here except `sparing`, and tell the other pods."""
        self.wake_locally(topic, sparing)
        self._publish(topic)

    def wake_locally(self, topic: Topic, sparing: Registration | None = None) -> None:
        """Wake every registration of the topic here except `sparing`."""
        for registration in tuple(self._registrations.get(topic, ())):
            if registration is not sparing:
                registration.wake()

    def wake_all(self) -> None:
        every = dict.fromkeys(registration for listening in self._registrations.values() for registration in listening)
        for registration in every:
            registration.wake()


class WakeChannel(Protocol):  # pragma: no cover - a port's method bodies are signatures
    """The channel on which the pods tell one another which topic changed: tandem's `WakeChannel` is its adapter."""

    async def publish(self, address: str) -> None: ...

    def received(self) -> AsyncIterator[Wake | Resubscribed]: ...


class SharedWakes:
    """The wakes between pods on one channel: a topic woken here reaches the streams of every pod that follows it, and
    a pod that missed wakes re-reads everything it serves when its subscription comes back.

    The publishing pod hears its own wake too, which only wakes a stream once more: a stream sends nothing for a read
    that changes nothing.
    """

    def __init__(self, channel: WakeChannel, *, end_process: Callable[[], None]) -> None:
        self._channel = channel
        self._end_process = end_process
        self._pending: set[asyncio.Task[None]] = set()

    def publish(self, topic: Topic) -> None:
        """Tell the other pods that `topic` changed, in a task of its own, so that the change never waits for Redis."""
        task = asyncio.get_running_loop().create_task(self._publish(_address_of(topic)))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def drain(self) -> None:
        """Wait for the publishes that are still on their way."""
        await asyncio.gather(*self._pending)

    @asynccontextmanager
    async def following(self, wakes: WakeList) -> AsyncGenerator[None]:
        """Follow the channel into `wakes` while the body runs; it starts once the first subscription is acknowledged,
        before which this pod is deaf to wakes, and refuses to start without one within `STARTUP_SECONDS`.
        """
        subscribed = asyncio.Event()
        follower = asyncio.create_task(self._follow(wakes, subscribed))
        try:
            await self._until_subscribed(follower, subscribed)
            yield
        finally:
            follower.cancel()
            # A failure of the channel is logged where it happened.
            with suppress(asyncio.CancelledError, StoreError):
                await follower
            await self.drain()

    async def _until_subscribed(self, follower: asyncio.Task[None], subscribed: asyncio.Event) -> None:
        acknowledged = asyncio.create_task(subscribed.wait())
        try:
            await asyncio.wait({follower, acknowledged}, timeout=STARTUP_SECONDS, return_when=asyncio.FIRST_COMPLETED)
        finally:
            acknowledged.cancel()
        if follower.done():
            # The channel failed before it was ready: its error stops the start.
            follower.result()
        if not subscribed.is_set():
            message = "the wake channel did not acknowledge its subscription: check redis_url"
            raise StartRefusedError(message)

    async def _follow(self, wakes: WakeList, subscribed: asyncio.Event) -> None:
        try:
            async for event in self._channel.received():
                if isinstance(event, Resubscribed):
                    subscribed.set()
                    wakes.wake_all()
                elif (topic := _topic_of(event.address)) is not None:
                    wakes.wake_locally(topic)
        except StoreError as failure:
            # The failure's message may carry an address, so only its type is logged.
            log.error("wake channel lost", error=type(failure).__name__)
            if subscribed.is_set():
                self._end_process()
            raise

    async def _publish(self, address: str) -> None:
        for attempt in range(_PUBLISH_ATTEMPTS):
            try:
                await self._channel.publish(address)
            except StoreError as failure:
                # A failure leaves the delivery uncertain, and a duplicate wake is harmless.
                last = attempt == _PUBLISH_ATTEMPTS - 1
                (log.error if last else log.warning)("wake publish failed", error=type(failure).__name__)
            else:
                return
