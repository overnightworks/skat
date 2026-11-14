from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


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


class WakeList:
    """Which wakes listen to which topic. A wake carries no data: the woken stream reads its own state again.

    Used on the event loop's thread only, so it takes no lock.
    """

    def __init__(self) -> None:
        self._registrations: dict[Topic, list[Registration]] = {}

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
        """Wake every registration of the topic except `sparing`."""
        for registration in tuple(self._registrations.get(topic, ())):
            if registration is not sparing:
                registration.wake()

    def wake_all(self) -> None:
        every = dict.fromkeys(registration for listening in self._registrations.values() for registration in listening)
        for registration in every:
            registration.wake()
