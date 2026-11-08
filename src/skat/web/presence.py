import asyncio
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final, Protocol

import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable
    from contextlib import AbstractContextManager

CHAIR_RELEASE_RETRY_SECONDS: Final = 15

log = structlog.get_logger()


@dataclass(frozen=True, eq=False)
class Subscription:
    """One open stream. `wake` only signals that its view changed; the stream rebuilds the view itself."""

    table_id: str
    account_id: str
    wake: Callable[[], None]


class Scheduler(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def schedule(self, delay: float, action: Callable[[], Awaitable[None]]) -> None:
        """Run `action` once after `delay` seconds; call it on the event loop's thread."""
        ...

    def cancel_all(self) -> None: ...


class LoopScheduler:
    """The event loop's timers: one task per scheduled action."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(self, delay: float, action: Callable[[], Awaitable[None]]) -> None:
        task = asyncio.get_running_loop().create_task(self._after(delay, action))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def cancel_all(self) -> None:
        for task in self._tasks:
            task.cancel()

    @staticmethod
    async def _after(delay: float, action: Callable[[], Awaitable[None]]) -> None:
        await asyncio.sleep(delay)
        await action()


@dataclass(frozen=True)
class ChairHold:
    """How long an away member keeps the chair, on whose clock and timers, and the command that frees it.

    `free_chair(table_id, account_id, due)` answers whether it freed the chair, and raises when the store
    fails. It enters `due` in its worker around the whole write, the commit included, and frees nothing when
    it yields False.
    """

    seconds: float
    clock: Callable[[], float]
    scheduler: Scheduler
    free_chair: Callable[[str, str, AbstractContextManager[bool]], Awaitable[bool]]


class Presence:
    """Who is connected to which table, in this process only, and since when each away member has been gone.

    The event loop owns every write, and a worker only reads, inside `due`. A wake carries no data: a stream
    that falls behind finds several changes folded into one wake and reads the latest state, which is its
    fresh snapshot.

    An account whose last stream on a table ended gets one timer; when it fires the chair is freed unless the
    account came back or left again since, which a newer leave time shows, or the presence has stopped. The
    check inside `due` and a reconnect order themselves under `_state`, which guards only dictionary
    operations and is never held across the write. A reconnect before the check wins; one after it awaits the
    commit, so it finds the chair freed instead of losing it unseen, and the event loop is never blocked.
    Leave times are not stored, so `hold_chairs` counts every seated member as having left when the server
    starts.
    """

    def __init__(self, hold: ChairHold) -> None:
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._stopped = False
        self._hold = hold
        self._left_at: dict[tuple[str, str], float] = {}
        self._state = threading.Lock()
        self._committing: dict[tuple[str, str], asyncio.Event] = {}

    @property
    def stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        """Wake every open stream to end and cancel every pending check; a later stream ends at once."""
        with self._state:
            self._stopped = True
        self._hold.scheduler.cancel_all()
        self._wake_all([subscription for open_ones in self._subscriptions.values() for subscription in open_ones])

    def wake_table(self, table_id: str) -> None:
        """Tell every stream of a table that a committed write changed its view; call it after the commit."""
        self._wake_all(list(self._subscriptions.get(table_id, ())))

    def connected(self, table_id: str) -> frozenset[str]:
        return frozenset(subscription.account_id for subscription in self._subscriptions.get(table_id, ()))

    def hold_chairs(self, occupied: Iterable[tuple[str, str]]) -> None:
        """Start the hold of every occupied chair, given as (table id, account id), at the server's start."""
        for table_id, account_id in occupied:
            self._start_hold(table_id, account_id)

    async def subscribe(self, table_id: str, account_id: str, wake: Callable[[], None]) -> Subscription:
        """Register before the stream reads its view, so a change after this call wakes it.

        Waits for a freeing of this member's chair whose check already passed to commit first.
        """
        with self._state:
            self._left_at.pop((table_id, account_id), None)
            committing = self._committing.get((table_id, account_id))
        if committing is not None:
            await committing.wait()
        subscription = Subscription(table_id, account_id, wake)
        already_connected = account_id in self.connected(table_id)
        others = list(self._subscriptions.get(table_id, ()))
        self._subscriptions.setdefault(table_id, []).append(subscription)
        if not already_connected:
            self._wake_all(others)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        remaining = self._subscriptions.get(subscription.table_id, [])
        if subscription not in remaining:
            return
        remaining.remove(subscription)
        if not remaining:
            del self._subscriptions[subscription.table_id]
        if subscription.account_id not in self.connected(subscription.table_id):
            self._start_hold(subscription.table_id, subscription.account_id)
            self._wake_all(remaining)

    def _start_hold(self, table_id: str, account_id: str) -> None:
        if self._stopped:
            return
        left_at = self._hold.clock()
        with self._state:
            self._left_at[table_id, account_id] = left_at
        self._hold.scheduler.schedule(self._hold.seconds, partial(self._expire, table_id, account_id, left_at))

    async def _expire(self, table_id: str, account_id: str, left_at: float) -> None:
        if not self._is_latest_leave(table_id, account_id, left_at):
            return
        committing = asyncio.Event()
        try:
            freed = await self._hold.free_chair(
                table_id, account_id, self._while_latest_leave(table_id, account_id, left_at, committing)
            )
        except Exception as failure:
            # The failure's message may carry the account id, so only its type is logged.
            log.error("chair release failed", table_id=table_id, error=type(failure).__name__)
            self._hold.scheduler.schedule(
                CHAIR_RELEASE_RETRY_SECONDS, partial(self._expire, table_id, account_id, left_at)
            )
            return
        finally:
            with self._state:
                self._committing.pop((table_id, account_id), None)
            committing.set()
        if self._left_at.get((table_id, account_id)) == left_at:
            del self._left_at[table_id, account_id]
        if freed:
            self.wake_table(table_id)

    @contextmanager
    def _while_latest_leave(
        self, table_id: str, account_id: str, left_at: float, committing: asyncio.Event
    ) -> Generator[bool]:
        """Enter on a worker: yields whether the freeing is due and, if so, publishes it until the loop ends it."""
        with self._state:
            due = self._is_latest_leave(table_id, account_id, left_at)
            if due:
                self._committing[table_id, account_id] = committing
        yield due

    def _is_latest_leave(self, table_id: str, account_id: str, left_at: float) -> bool:
        return not self._stopped and self._left_at.get((table_id, account_id)) == left_at

    @staticmethod
    def _wake_all(subscriptions: list[Subscription]) -> None:
        for subscription in subscriptions:
            subscription.wake()
