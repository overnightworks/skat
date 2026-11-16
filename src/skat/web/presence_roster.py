"""What the pods share about who streams: the port to the leases, one read of them and what an unreadable roster is."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn, Protocol

from skat.web.stream_holder import StreamHolder

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from contextlib import AbstractAsyncContextManager
    from datetime import timedelta

    from tandem import Hold, Lapse, Roster


class PresenceUnknownError(Exception):
    """Who is present could not be read, or cannot yet vouch for an absence: nothing is freed, ended or noted on it."""


class StreamLeases(Protocol):  # pragma: no cover - a port's method bodies are signatures; tandem's `Leases` runs
    """The presence leases the pods share: tandem's `Leases` is its adapter."""

    def kept(self, holder: str, *, every: timedelta) -> AbstractAsyncContextManager[Hold]: ...

    async def live(self) -> Roster: ...

    async def serve_lapses(
        self,
        handle: Callable[[Lapse], Awaitable[None]],  # noqa: V107 the port's parameter names are tandem's
        *,
        claimer: str,  # noqa: V107 the port's parameter names are tandem's
        every: timedelta,
    ) -> NoReturn: ...


@dataclass(frozen=True)
class Present:
    """Who streams at which tables on any pod, from one read of the shared leases; `settled` says whether a person
    missing from it is gone and not lost with a restart of the store.
    """

    by_table: Mapping[str, frozenset[str]]
    settled: bool

    def at(self, table_id: str) -> frozenset[str]:
        return self.by_table.get(table_id, frozenset())

    @classmethod
    def of(cls, roster: Roster) -> Present:
        by_table: dict[str, set[str]] = {}
        for holder in map(StreamHolder.parse, roster.holders):
            by_table.setdefault(holder.table_id, set()).add(holder.account_id)
        return cls({table_id: frozenset(accounts) for table_id, accounts in by_table.items()}, roster.settled)
