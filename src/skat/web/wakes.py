import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final, Protocol

import structlog
from tandem import StoreError, Wake

from skat.web.secret_files import StartRefusedError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterable
    from contextlib import AbstractAsyncContextManager

# How long a pod waits at its start for its first subscription to the channel, so that a wrong URL fails loud instead
# of hanging; the platform's liveness window is longer.
STARTUP_SECONDS: Final = 10

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

    def following(
        self,
        *,
        on_resync: Callable[[], None],  # noqa: V107 a port signature names the keywords its adapter takes
        on_wake: Callable[[Wake], None],  # noqa: V107 a port signature names the keywords its adapter takes
        on_failed: Callable[[Exception], None],  # noqa: V107 a port signature names the keywords its adapter takes
        ready_within: timedelta,  # noqa: V107 a port signature names the keywords its adapter takes
    ) -> AbstractAsyncContextManager[None]: ...


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
        """Follow the channel into `wakes` while the body runs. Before the subscription is confirmed a channel failure
        refuses the start, as does no confirmation within `STARTUP_SECONDS`; after it a failure ends the process.
        """

        def wake_locally(wake: Wake) -> None:
            if (topic := _topic_of(wake.address)) is not None:
                wakes.wake_locally(topic)

        async with AsyncExitStack() as stack:
            try:
                await stack.enter_async_context(
                    self._channel.following(
                        on_resync=wakes.wake_all,
                        on_wake=wake_locally,
                        on_failed=lambda _failure: self._end_process(),
                        ready_within=timedelta(seconds=STARTUP_SECONDS),
                    )
                )
            except StoreError as failure:
                message = f"the wake channel was not ready ({type(failure).__name__}): check redis_url"
                raise StartRefusedError(message) from failure
            try:
                yield
            finally:
                await self.drain()

    async def _publish(self, address: str) -> None:
        try:
            await self._channel.publish(address)
        except StoreError as failure:
            # The failure's message may carry an address, so only its type is logged.
            log.error("wake_publish.failed", error_type=type(failure).__name__)
