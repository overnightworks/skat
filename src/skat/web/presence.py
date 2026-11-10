import asyncio
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final, Protocol

import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable, Mapping
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
class AgentLease:
    """How long an agent's admitted call counts as its presence, and how to read where it sits.

    `seated_tables(account_id)` answers the ids of the tables the account holds a chair at, and raises when the
    store fails; the presence reads it only when a lease starts or lapses.
    """

    seconds: float
    seated_tables: Callable[[str], Awaitable[Iterable[str]]]


@dataclass(frozen=True)
class NextDeal:
    """How long a table pauses after a passed-in hand, and the command that deals the next one.

    `deal(table_id, connected_accounts)` answers whether it dealt, and raises when the store fails. It enters
    `connected_accounts` in its worker once it holds the table and leaves it after the commit; that yields who is
    connected then, and None once the presence has stopped.
    """

    seconds: float
    deal: Callable[[str, AbstractContextManager[frozenset[str] | None]], Awaitable[bool]]


@dataclass(frozen=True)
class EmptyTable:
    """How long a table nobody is connected to stays, the command that ends it and the one that notes who is there.

    `end(table_id, connected_accounts)` answers whether it ended the table, and raises when the store fails. It
    enters `connected_accounts` in its worker once it holds the table and leaves it after the commit; that yields
    who is connected then, and None once the presence has stopped or a stream opened since the wait began.

    `note(table_id, connected_accounts)` stores since when nobody has been at the table, called wherever who is
    connected changes. It answers whether the table ended because someone arrived after the wait was up, enters
    `connected_accounts` as `end` does, and raises when the store fails.
    """

    seconds: float
    end: Callable[[str, AbstractContextManager[frozenset[str] | None]], Awaitable[bool]]
    note: Callable[[str, AbstractContextManager[frozenset[str] | None]], Awaitable[bool]]


class Presence:
    """Who is connected to which table, in this process only, and since when each away member has been gone.

    The event loop owns every write to the subscriptions and makes it under `_state`, so a deal's worker can read
    them there. Otherwise a worker touches only the leave times, the committing markers and the lease ends, all
    under `_state`: inside `due` and in `restart_leaves`, and where `TableService`'s worker reads `live_leases`. A
    wake carries no data: a stream that falls behind finds several changes folded into one wake and reads the
    latest state, which is its fresh snapshot.

    An account whose last stream on a table ended gets one timer; when it fires the chair is freed unless the
    account came back or left again since, which a newer leave time shows, or the presence has stopped. The
    check inside `due` and a reconnect order themselves under `_state`, which guards only dictionary
    operations and is never held across the write. A reconnect before the check wins; one after it awaits the
    commit, so it finds the chair freed instead of losing it unseen, and the event loop is never blocked.
    Leave times are not stored, so `hold_chairs` counts every seated member as having left when the server
    starts.

    After a passed-in hand a table gets one pause; when it ends, the deal is asked for with who is connected
    then, and a stream's first view of the table starts the next pause if none is pending. After a played game
    the deal is asked for at once, with no pause, whenever a caller may have made it due; a lease start asks
    through `deal_soon`, after the pause. A later hand's end replaces a pending pause, and the
    replaced timer does nothing when it fires, so a pending timer of an earlier hand cannot shorten this one's.
    Nothing about a pause is stored: after a restart none is pending, and all three being connected can only become
    true by streams opening or an agent's call starting its lease, so no sweep is needed.

    An agent holds no stream: every admitted call of it renews its lease, and while the lease runs the agent counts
    as present at the tables it sits at (`live_leases`; the table's rule intersects them with its occupants). One
    timer per lease re-arms itself to the lease's end. A lapse is the agent's leave from each of its tables: the
    streams are woken, a hold starts as for a person and a table with no stream open waits afresh; a pending hold
    never frees a chair while a lease runs. Leases are in this process only, like streams, and gone at a restart.

    A table gets one wait when it is created or found at the server's start, and another each time its last stream
    ends or a chair is freed where no stream is open and a lease runs. An opening or a sit where no stream is open
    and a lease runs notes who is present, as a lease does; it keeps a wait that is pending and starts one when
    none is (watch_empty_table). A stand-up there owes a full wait from itself. A stream that opens ends the wait,
    so the pending timer finds itself superseded and does nothing. When it fires, the end is asked for with who is
    connected then, and a failure is retried while the wait stays the table's latest. Since when nobody has been
    at a table is stored: a table's last leave, a lease starting or lapsing and the first arrival note who is
    present, each on the table's row (presence notes an empty table and the service decides whether to stamp the
    time; an arrival or a lease start clears it), and the server's start seeds each table's wait with what is
    left of it, so a restart never gives a table a fresh wait it had already begun.
    """

    def __init__(self, hold: ChairHold, next_deal: NextDeal, empty_table: EmptyTable, lease: AgentLease) -> None:
        self._lease = lease
        self._lease_ends: dict[str, float] = {}
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._stopped = False
        self._hold = hold
        self._next_deal = next_deal
        self._empty_table = empty_table
        self._pauses: dict[str, object] = {}
        self._empty_waits: dict[str, object] = {}
        self._left_at: dict[tuple[str, str], float] = {}
        self._state = threading.Lock()
        self._committing: dict[tuple[str, str], asyncio.Event] = {}
        self._writing: set[asyncio.Event] = set()

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

    def live_leases(self) -> frozenset[str]:
        """The agents whose lease runs: a read with no side effect, which a worker may call under a table's lock."""
        with self._state:
            return frozenset(self._lease_ends)

    def hold_chairs(self, occupied: Iterable[tuple[str, str]]) -> None:
        """Start a fresh hold of each (table id, account id): at the server's start, and when a hand ends."""
        for table_id, account_id in occupied:
            self._start_hold(table_id, account_id)

    def renew_lease(self, account_id: str) -> None:
        """Count the account as present at every table it sits at for one more lease; call it on the event loop's
        thread for every admitted call of an agent.

        A lease that starts has its tables woken and their next deal asked for; one timer per lease re-arms itself
        until the lease has run out without a renewal.
        """
        if self._stopped:
            return
        ends = self._hold.clock() + self._lease.seconds
        with self._state:
            starts = account_id not in self._lease_ends
            self._lease_ends[account_id] = ends
        if starts:
            self._hold.scheduler.schedule(self._lease.seconds, partial(self._check_lease, account_id))
            self._hold.scheduler.schedule(0, partial(self._settle_lease, account_id, lapsed=False))

    async def _check_lease(self, account_id: str) -> None:
        remaining = self._lease_ends[account_id] - self._hold.clock()
        if remaining > 0:
            self._hold.scheduler.schedule(remaining, partial(self._check_lease, account_id))
            return
        with self._state:
            del self._lease_ends[account_id]
        await self._settle_lease(account_id, lapsed=True)

    async def _settle_lease(self, account_id: str, *, lapsed: bool) -> None:
        """Act on every table the account sits at after its lease started or lapsed, from one read of them.

        A lapse wakes the streams, starts the chair's hold and, where no stream is open, a fresh wait for the empty
        table; a start wakes them and asks for the next deal. A failed read is retried while the lease still is in
        the state that was acted on.
        """
        if self._stopped or (account_id in self._lease_ends) == lapsed:
            return
        try:
            table_ids = list(await self._lease.seated_tables(account_id))
        except Exception as failure:
            # The failure's message may carry the account id, so only its type is logged.
            log.error("lease tables read failed", error=type(failure).__name__)
            self._hold.scheduler.schedule(
                CHAIR_RELEASE_RETRY_SECONDS, partial(self._settle_lease, account_id, lapsed=lapsed)
            )
            return
        for table_id in table_ids:
            self.wake_table(table_id)
            self._note_soon(table_id)
            if not lapsed:
                self.deal_soon(table_id)
                continue
            self._start_hold(table_id, account_id)
            if table_id not in self._subscriptions:
                self._start_empty_wait(table_id)

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
            self._empty_waits.pop(table_id, None)
            self._subscriptions.setdefault(table_id, []).append(subscription)
        if not others:
            try:
                ended = await self._empty_table.note(
                    table_id, self._connected_while_writing(table_id, asyncio.get_running_loop())
                )
            except BaseException:
                self.unsubscribe(subscription)
                if table_id in self._subscriptions:
                    self._note_soon(table_id)
                raise
            if ended:
                self.wake_table(table_id)
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
        if subscription.table_id not in self._subscriptions:
            self._start_empty_wait(subscription.table_id)
            self._note_soon(subscription.table_id)

    def watch_empty_table(self, table_id: str, seconds_left: float | None = None) -> None:
        """Start a table's wait if nobody is connected and none is pending: a create retry neither restarts nor
        stretches it. Routes reach it through chair_taken, on the event loop's thread; the server's start calls it
        for each live table with what is left of its wait.
        """
        if table_id not in self._subscriptions and table_id not in self._empty_waits:
            self._start_empty_wait(table_id, seconds_left)

    def chair_taken(self, table_id: str) -> None:
        """A command opened a table or seated someone at it; call it on the event loop's thread after the commit.

        The table waits for its end unless a wait is pending. Where no stream is open and a lease runs, the lease may
        have joined the table without any stream changing, so who is present is noted on the table's row.
        """
        if table_id in self._subscriptions:
            return
        self.watch_empty_table(table_id)
        if self.live_leases():
            self._note_soon(table_id)

    def chair_freed(self, table_id: str) -> None:
        """A command freed a chair; call it on the event loop's thread after the commit.

        Where no stream is open and a lease runs, the chair may have been the only one a lease made present: the
        table gets a full wait from now, as when its last stream ends or a lease lapses, and who is present is noted
        on the table's row. With no lease running, only a stream makes anyone present, and the table already waits.
        """
        if table_id in self._subscriptions or not self.live_leases():
            return
        self._start_empty_wait(table_id)
        self._note_soon(table_id)

    def watch_empty_tables(self, seconds_left_by_table: Mapping[str, float]) -> None:
        """Start the wait of each live table found at the server's start with what is left of it."""
        for table_id, seconds_left in seconds_left_by_table.items():
            self.watch_empty_table(table_id, seconds_left)

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
        await self.deal_now(table_id)

    async def deal_now(self, table_id: str) -> None:
        """Ask for a table's next deal with no pause; the table's own rule decides under its row lock.

        A failure is logged and changes nothing, so the next request asks again.
        """
        try:
            dealt = await self._next_deal.deal(
                table_id, self._connected_while_writing(table_id, asyncio.get_running_loop())
            )
        except Exception as failure:
            # The failure's message may carry an account id, so only its type is logged.
            log.error("next deal failed", table_id=table_id, error=type(failure).__name__)
            return
        if dealt:
            self.wake_table(table_id)

    def _start_empty_wait(self, table_id: str, seconds: float | None = None) -> None:
        if self._stopped:
            return
        wait = object()
        with self._state:
            self._empty_waits[table_id] = wait
        self._hold.scheduler.schedule(
            self._empty_table.seconds if seconds is None else seconds, partial(self._end_if_empty, table_id, wait)
        )

    def _note_soon(self, table_id: str, delay_seconds: float = 0) -> None:
        if self._stopped:
            return
        self._hold.scheduler.schedule(delay_seconds, partial(self._note_presence, table_id))

    async def _note_presence(self, table_id: str) -> None:
        """Store who is present now, read once the row is locked; a failure is retried while the presence runs."""
        try:
            ended = await self._empty_table.note(
                table_id, self._connected_while_writing(table_id, asyncio.get_running_loop())
            )
        except Exception as failure:
            # The failure's message may carry an account id, so only its type is logged.
            log.error("empty since write failed", table_id=table_id, error=type(failure).__name__)
            self._note_soon(table_id, CHAIR_RELEASE_RETRY_SECONDS)
            return
        if ended:
            self.wake_table(table_id)

    async def _end_if_empty(self, table_id: str, wait: object) -> None:
        if not self._is_latest_wait(table_id, wait):
            return
        loop = asyncio.get_running_loop()
        try:
            ended = await self._empty_table.end(
                table_id, self._connected_while_writing(table_id, loop, partial(self._is_latest_wait, table_id, wait))
            )
        except Exception as failure:
            # The failure's message may carry an account id, so only its type is logged.
            log.error("empty table end failed", table_id=table_id, error=type(failure).__name__)
            self._hold.scheduler.schedule(CHAIR_RELEASE_RETRY_SECONDS, partial(self._end_if_empty, table_id, wait))
            return
        with self._state:
            if self._empty_waits.get(table_id) is wait:
                del self._empty_waits[table_id]
        if ended:
            self.wake_table(table_id)

    def _is_latest_wait(self, table_id: str, wait: object) -> bool:
        return not self._stopped and self._empty_waits.get(table_id) is wait

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
    def _connected_while_writing(
        self, table_id: str, loop: asyncio.AbstractEventLoop, is_due: Callable[[], bool] = lambda: True
    ) -> Generator[frozenset[str] | None]:
        """Enter on a worker once it holds the table: yields who is connected then, and None once stopped or when
        `is_due` says the caller's request has been superseded.

        The exit runs on the worker after the commit, so `finish_writes` outlives a cancelled event-loop task.
        """
        committing = asyncio.Event()
        with self._state:
            due = not self._stopped and is_due()
            connected = self.connected(table_id) if due else None
            if due:
                self._writing.add(committing)
        try:
            yield connected
        finally:
            if due:
                with self._state:
                    self._writing.discard(committing)
                loop.call_soon_threadsafe(committing.set)

    async def finish_writes(self) -> None:
        """Wait until every freeing whose check passed and every deal or end that read its accounts has ended its
        transaction; call it after `stop`.
        """
        with self._state:
            writing = [*self._committing.values(), *self._writing]
        for committing in writing:
            await committing.wait()

    def _is_latest_leave(self, table_id: str, account_id: str, left_at: float) -> bool:
        return (
            not self._stopped
            and account_id not in self._lease_ends
            and self._left_at.get((table_id, account_id)) == left_at
        )

    @staticmethod
    def _wake_all(subscriptions: list[Subscription]) -> None:
        for subscription in subscriptions:
            subscription.wake()
