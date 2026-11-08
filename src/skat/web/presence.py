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
# Long enough to read „Eingepasst“.
NEXT_DEAL_PAUSE_SECONDS: Final = 4

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
    fails. It enters `due` in its worker once it holds the table, leaves it after the commit, and frees nothing
    when it yields False.
    """

    seconds: float
    clock: Callable[[], float]
    scheduler: Scheduler
    free_chair: Callable[[str, str, AbstractContextManager[bool]], Awaitable[bool]]


@dataclass(frozen=True)
class NextDeal:
    """How long a table pauses after a passed-in hand, and the command that deals the next one.

    `deal(table_id, connected_accounts)` answers whether it dealt, and raises when the store fails. It enters
    `connected_accounts` in its worker once it holds the table and leaves it after the commit; that yields who is
    connected then, and nobody once the presence has stopped.
    """

    seconds: float
    deal: Callable[[str, AbstractContextManager[frozenset[str]]], Awaitable[bool]]


class Presence:
    """Who is connected to which table, in this process only, and since when each away member has been gone.

    The event loop owns every write to the subscriptions and makes it under `_state`, so a deal's worker can read
    them there. Otherwise a worker touches only the leave times and the committing markers, under `_state`, inside
    `due` and in `restart_leaves`. A wake carries no data: a stream that falls behind finds several changes folded
    into one wake and reads the latest state, which is its fresh snapshot.

    An account whose last stream on a table ended gets one timer; when it fires the chair is freed unless the
    account came back or left again since, which a newer leave time shows, or the presence has stopped. The
    check inside `due` and a reconnect order themselves under `_state`, which guards only dictionary
    operations and is never held across the write. A reconnect before the check wins; one after it awaits the
    commit, so it finds the chair freed instead of losing it unseen, and the event loop is never blocked.
    Leave times are not stored, so `hold_chairs` counts every seated member as having left when the server
    starts.

    After a passed-in hand a table gets one pause; when it ends, the deal is asked for with who is connected
    then, and a stream's first view of the table starts the next pause if none is pending. A later hand's end
    replaces a pending pause, and the replaced timer does nothing when it fires, so a pause that belonged to an
    earlier hand never shortens this one's. Nothing about a pause is stored: after a restart none is pending, and
    all three being connected can only become true by streams opening, so no sweep is needed.
    """

    def __init__(self, hold: ChairHold, next_deal: NextDeal) -> None:
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._stopped = False
        self._hold = hold
        self._next_deal = next_deal
        self._pauses: dict[str, object] = {}
        self._left_at: dict[tuple[str, str], float] = {}
        self._state = threading.Lock()
        self._committing: dict[tuple[str, str], asyncio.Event] = {}
        self._dealing: set[asyncio.Event] = set()

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
        """Start a fresh hold of each (table id, account id): at the server's start, and when a hand ends."""
        for table_id, account_id in occupied:
            self._start_hold(table_id, account_id)

    def restart_leaves(self, table_id: str, account_ids: Iterable[str]) -> None:
        """Give each account a newer leave time than any pending timer knows; call it on a worker inside the
        transaction that ended a hand, so a freeing that reaches the table after the commit finds itself superseded.
        """
        left_at = self._hold.clock()
        with self._state:
            for account_id in account_ids:
                self._left_at[table_id, account_id] = left_at

    async def subscribe(self, table_id: str, account_id: str, wake: Callable[[], None]) -> Subscription:
        """Register before the stream reads its view, so a change after this call wakes it.

        Waits for a freeing of this member's chair whose check already passed to commit first. The leave stays
        recorded while it waits, so a waiter that is cancelled leaves the freeing's retry intact.
        """
        key = (table_id, account_id)
        with self._state:
            committing = self._committing.get(key)
            if committing is None:
                self._left_at.pop(key, None)
        if committing is not None:
            await committing.wait()
            with self._state:
                self._left_at.pop(key, None)
        subscription = Subscription(table_id, account_id, wake)
        already_connected = account_id in self.connected(table_id)
        others = list(self._subscriptions.get(table_id, ()))
        with self._state:
            self._subscriptions.setdefault(table_id, []).append(subscription)
        if not already_connected:
            self._wake_all(others)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        remaining = self._subscriptions.get(subscription.table_id, [])
        if subscription not in remaining:
            return
        with self._state:
            remaining.remove(subscription)
            if not remaining:
                del self._subscriptions[subscription.table_id]
        if subscription.account_id not in self.connected(subscription.table_id):
            self._start_hold(subscription.table_id, subscription.account_id)
            self._wake_all(remaining)

    def deal_soon(self, table_id: str) -> None:
        """Start the pause before a table's next deal; a request during a pending one neither cuts nor stretches it."""
        if table_id not in self._pauses:
            self.restart_deal_pause(table_id)

    def restart_deal_pause(self, table_id: str) -> None:
        """Start a table's pause from now, whatever was pending: a hand ended, and its pause is its own."""
        if self._stopped:
            return
        pause = object()
        self._pauses[table_id] = pause
        self._hold.scheduler.schedule(self._next_deal.seconds, partial(self._deal_after_pause, table_id, pause))

    async def _deal_after_pause(self, table_id: str, pause: object) -> None:
        if self._pauses.get(table_id) is not pause:
            return
        # The pause is over before the deal is asked for, so a stream that opens while the deal runs and finds the
        # table still passed in starts the next pause instead of waiting on an answer that left it out.
        del self._pauses[table_id]
        try:
            dealt = await self._next_deal.deal(
                table_id, self._connected_while_dealing(table_id, asyncio.get_running_loop())
            )
        except Exception as failure:
            # The failure's message may carry an account id, so only its type is logged.
            log.error("next deal failed", table_id=table_id, error=type(failure).__name__)
            return
        if dealt:
            self.wake_table(table_id)

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
        try:
            freed = await self._hold.free_chair(
                table_id,
                account_id,
                self._while_latest_leave(table_id, account_id, left_at, asyncio.get_running_loop()),
            )
        except Exception as failure:
            # The failure's message may carry the account id, so only its type is logged.
            log.error("chair release failed", table_id=table_id, error=type(failure).__name__)
            self._hold.scheduler.schedule(
                CHAIR_RELEASE_RETRY_SECONDS, partial(self._expire, table_id, account_id, left_at)
            )
            return
        if self._left_at.get((table_id, account_id)) == left_at:
            del self._left_at[table_id, account_id]
        if freed:
            self.wake_table(table_id)

    @contextmanager
    def _while_latest_leave(
        self, table_id: str, account_id: str, left_at: float, loop: asyncio.AbstractEventLoop
    ) -> Generator[bool]:
        """Enter on a worker: yields whether the freeing is due; while it is, a reconnect awaits the exit.

        The exit runs on the worker after the commit, so the marker outlives a cancelled event-loop task.
        """
        committing = asyncio.Event()
        with self._state:
            due = self._is_latest_leave(table_id, account_id, left_at)
            if due:
                self._committing[table_id, account_id] = committing
        try:
            yield due
        finally:
            if due:
                with self._state:
                    self._committing.pop((table_id, account_id), None)
                loop.call_soon_threadsafe(committing.set)

    @contextmanager
    def _connected_while_dealing(self, table_id: str, loop: asyncio.AbstractEventLoop) -> Generator[frozenset[str]]:
        """Enter on a worker once it holds the table: yields who is connected then, and nobody once stopped.

        The exit runs on the worker after the commit, so `finish_writes` outlives a cancelled event-loop task.
        """
        committing = asyncio.Event()
        with self._state:
            may_deal = not self._stopped
            connected = self.connected(table_id) if may_deal else frozenset[str]()
            if may_deal:
                self._dealing.add(committing)
        try:
            yield connected
        finally:
            if may_deal:
                with self._state:
                    self._dealing.discard(committing)
                loop.call_soon_threadsafe(committing.set)

    async def finish_writes(self) -> None:
        """Wait until every freeing whose check passed and every deal that read its accounts has ended its transaction;
        call it after `stop`.
        """
        with self._state:
            writing = [*self._committing.values(), *self._dealing]
        for committing in writing:
            await committing.wait()

    def _is_latest_leave(self, table_id: str, account_id: str, left_at: float) -> bool:
        return not self._stopped and self._left_at.get((table_id, account_id)) == left_at

    @staticmethod
    def _wake_all(subscriptions: list[Subscription]) -> None:
        for subscription in subscriptions:
            subscription.wake()
