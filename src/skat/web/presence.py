import asyncio
import math
import threading
import uuid
from concurrent.futures import CancelledError
from contextlib import AsyncExitStack, contextmanager
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Final, NoReturn, Protocol

import structlog
from logline import unit_trace

from skat.web.presence_line import PresenceTimer, TimerRuns
from skat.web.presence_roster import PresenceUnknownError, Present, StreamLeases
from skat.web.reaction_log import ReactionLog
from skat.web.stream_holder import StreamHolder
from skat.web.waits import AskClock
from skat.web.wakes import Registration, TableTopic, WakeList

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Generator, Iterable, Mapping
    from concurrent.futures import Future
    from contextlib import AbstractContextManager

    from tandem import Lapse

CHAIR_RELEASE_RETRY_SECONDS: Final = 15
# Long enough to read „Eingepasst“.
NEXT_DEAL_PAUSE_SECONDS: Final = 4
# An open stream renews its lease this often and the pods sweep lapsed leases this often; the leases last longer than
# a renewal, so a pod that dies loses its people within the lease plus one sweep.
STREAM_RENEWAL_EVERY: Final = timedelta(seconds=10)
LAPSE_SWEEP_EVERY: Final = timedelta(seconds=5)
# A worker holding a table's row lock waits this long for the roster before the presence counts it as unknown.
ROSTER_READ_TIMEOUT_SECONDS: Final = 3
# Every pod looks for due chair holds this often, so a chair is freed at most this late.
HOLD_SWEEP_EVERY_SECONDS: Final = 5

log = structlog.get_logger()


@dataclass(frozen=True, eq=False)
class Subscription:
    """One open stream: its account is connected at the table, its wake-list registration wakes it and its lease
    keeps it counted on every pod.
    """

    holder: StreamHolder
    registration: Registration
    lease: AsyncExitStack

    @property
    def table_id(self) -> str:
        return self.holder.table_id

    @property
    def account_id(self) -> str:
        return self.holder.account_id


async def _finished_despite_cancellation(work: Coroutine[object, object, None]) -> None:
    """Run `work` to its end however often the caller is cancelled, then propagate the cancellation."""
    task = asyncio.ensure_future(work)
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.wait((task,))
        except asyncio.CancelledError as cancelled:  # NOSONAR(S7497) re-raised once the work ends
            cancellation = cancelled
    task.result()
    if cancellation is not None:
        raise cancellation


class Scheduler(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def schedule(self, delay: float, action: Callable[[], Awaitable[None]]) -> None:
        """Run `action` once after `delay` seconds; call it on the event loop's thread."""
        ...

    def cancel_all(self) -> None: ...


class LoopScheduler:
    """The event loop's timers: one task per scheduled action, each run in a trace of its own."""

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
        # The task was made inside the request that scheduled it; a unit taken off a timer starts its own trace.
        with unit_trace(None):
            await action()


@dataclass(frozen=True)
class ChairHold:
    """The presence's clock and timers, and the stored chair holds; each call raises when the store fails.

    `leave(table_id, account_id)` stores the account's hold as due one hold from now, the newest leave on any pod
    winning, and stores nothing for an account without a chair at the live table. `lapse(table_id, account_id)` stores
    it the same way only where the account has no hold at the table. `clear(table_id, account_id)` drops
    it, and waits for a freeing of it in flight. `due()` answers the (table id, account id) of the holds due now, a
    candidate list. `free_chair(table_id, account_id, absent)` frees the chair of a due hold and drops the hold, once:
    it enters `absent` in its worker once it holds the table and the hold, leaves it after the commit, and answers
    whether it freed the chair. `absent` yields None once the presence has stopped, which keeps the hold.
    """

    clock: Callable[[], float]
    scheduler: Scheduler
    leave: Callable[[str, str], Awaitable[None]]
    lapse: Callable[[str, str], Awaitable[None]]
    clear: Callable[[str, str], Awaitable[None]]
    due: Callable[[], Awaitable[Iterable[tuple[str, str]]]]
    free_chair: Callable[[str, str, AbstractContextManager[bool | None]], Awaitable[bool]]


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


@dataclass(frozen=True)
class EndAnswers:
    """The step that ends a proposal to end the series once its minute is over.

    `lapse(table_id)` answers the seconds the table's proposal still has to wait, None once none stands, and raises
    when the store fails.
    """

    lapse: Callable[[str], Awaitable[float | None]]


class Presence:
    """Who is connected to which table on any pod, and when an away member's chair hold runs out.

    Every open stream holds a lease in the roster the pods share, so `connected` reads people across pods and counts
    an account once however many streams it has. The pod's own `_subscriptions` only say which streams to wake and
    when a decision may be due; every decision reads the roster again. The event loop owns every write to the
    subscriptions and makes it under `_state`. Otherwise a worker touches only the write markers and the lease ends,
    all under `_state`: inside a write's guard, and where `TableService`'s worker reads `live_leases`; it reads the
    roster before it takes `_state`, from the event loop that owns the client. A wake carries no data: a stream that
    falls behind finds several changes folded into one wake and reads the latest state, which is its fresh snapshot.

    A chair hold is a deadline in the store, on the store's clock, so it outlives the pod that wrote it. A stream that
    was the account's last at the table on any pod, or whose pod cannot read the roster, stores the account's leave
    before its lease ends, even while the presence stops; a stream lapsed on a dead pod and an agent's lapsed lease
    store it too, unless the account is back. A leave that cannot be stored is logged and stored again after
    `CHAIR_RELEASE_RETRY_SECONDS` while the presence runs; until then the chair is kept. An arrival clears the account's
    hold once its lease has started. Every pod sweeps the due holds every `HOLD_SWEEP_EVERY_SECONDS`; the freeing locks
    the table and the hold, and frees the chair only while the roster vouches that the account streams on no pod and no
    lease of it runs here. An arrival's clear waits for a freeing in flight, so it finds the chair freed instead of
    losing it unseen. Nothing is held anew at a start.

    After a passed-in hand a table gets one pause; when it ends, the deal is asked for with who is connected
    then, and a stream's first view of the table starts the next pause if none is pending. After a played game
    the deal is asked for at once, with no pause, whenever a caller may have made it due; a lease start asks
    through `deal_soon`, after the pause. A later hand's end replaces a pending pause, and the
    replaced timer does nothing when it fires, so a pending timer of an earlier hand cannot shorten this one's.
    Nothing about a pause is stored: after a restart none is pending, and all three being connected can only become
    true by streams opening or an agent's call starting its lease, so no sweep is needed. A deal that fails is asked
    for again after `CHAIR_RELEASE_RETRY_SECONDS` while the presence runs.

    An agent holds no stream: every admitted call of it renews its lease, and while the lease runs the agent counts
    as present at the tables it sits at (`live_leases`; the table's rule intersects them with its occupants). One
    timer per lease re-arms itself to the lease's end. A lapse is the agent's leave from each of its tables: the
    streams are woken, a hold starts as for a person and a table with no stream open waits afresh; a pending hold
    never frees a chair while a lease runs. An agent's leases are in the process that heard its call and gone at a
    restart.

    A table gets one wait when it is created or found at the server's start, and another each time its last stream
    ends or a chair is freed where no stream is open and a lease runs. An opening or a sit where no stream is open
    starts a wait when none is pending, whether a lease runs or not, and keeps a pending one (watch_empty_table);
    where a lease runs it also notes who is present, as a lease does. A stand-up there owes a full wait from itself.
    A stream that opens ends the wait, so the pending timer finds itself superseded and does nothing. When it fires,
    the end is asked for with who is connected then, and a failure is retried while the wait stays the table's
    latest. Since when nobody has been at a table is stored: a table's last leave, a lease starting or lapsing and
    the first arrival note who is present, each on the table's row (presence notes an empty table and the service
    decides whether to stamp the time; an arrival or a lease start has the service clear it, or end an undealt table
    whose wait is up), and the server's start seeds each table's wait with what is left of it, so a restart never
    gives a table a fresh wait it had already begun.

    `waits` is the one `AskClock` of the process and `reactions` the one `ReactionLog`, both on the chair hold's clock;
    the presence drops a table's entries where its end or note answers that the table ended.
    """

    def __init__(
        self,
        hold: ChairHold,
        next_deal: NextDeal,
        empty_table: EmptyTable,
        lease: AgentLease,
        wakes: WakeList,
        stream_leases: StreamLeases,
        end_answers: EndAnswers,
    ) -> None:
        self._end_answers = end_answers
        self._end_answer_dues: dict[str, float] = {}
        self._lease = lease
        self._stream_leases = stream_leases
        self._claimer = uuid.uuid4().hex
        self.waits = AskClock(hold.clock)
        self.reactions = ReactionLog(hold.clock)
        self._lease_ends: dict[str, float] = {}
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._wakes = wakes
        self._stopped = False
        self._hold = hold
        self._next_deal = next_deal
        self._empty_table = empty_table
        self._pauses: dict[str, object] = {}
        self._empty_waits: dict[str, object] = {}
        self._timer_runs = TimerRuns()
        self._state = threading.Lock()
        self._writing: set[asyncio.Event] = set()
        self._reads: set[Future[Present]] = set()

    @property
    def stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        """Wake every open stream to end and cancel every pending check; a later stream ends at once."""
        with self._state:
            self._stopped = True
            reading = list(self._reads)
        for read in reading:
            read.cancel()
        self._hold.scheduler.cancel_all()
        self._wakes.wake_all()

    def writing(self) -> AbstractContextManager[frozenset[str] | None]:
        """The guard of a write the server makes on its own account that asks nobody's presence: enter it on the
        worker once the row is locked, and it yields None once the presence has stopped. `finish_writes` waits for it
        to be left. Call it on the event loop.
        """
        return self._guarded_write(asyncio.get_running_loop(), lambda: frozenset())

    def wake_table(self, table_id: str) -> None:
        """Tell every stream of a table that a committed write changed its view; call it after the commit."""
        self._wakes.wake(TableTopic(table_id))

    async def connected(self, table_id: str) -> frozenset[str]:
        """Who streams at the table on any pod; it raises when the roster cannot be read."""
        return (await self._read_present()).at(table_id)

    async def connected_at(self, table_ids: Iterable[str]) -> dict[str, frozenset[str]]:
        """Who streams at each of the tables on any pod, from one read of the roster."""
        present = await self._read_present()
        return {table_id: present.at(table_id) for table_id in table_ids}

    async def _read_present(self) -> Present:
        return Present.of(await self._stream_leases.live())

    async def serve_lapses(self) -> NoReturn:
        """Store the leave of a stream that lapsed on a pod that did not end it and wake its table, on every pod,
        until cancelled. Every pod serves them; each lapse is claimed by one.
        """
        await self._stream_leases.serve_lapses(self._leave_lapsed, claimer=self._claimer, every=LAPSE_SWEEP_EVERY)

    async def _leave_lapsed(self, lapse: Lapse) -> None:
        """Store the leave only where no hold exists, since tandem queues a lapse for every lease that ends, a close's
        too; a leave that cannot be stored raises, so tandem hands the lapse again once its claim runs out.
        """
        holder = StreamHolder.parse(lapse.holder)
        if not await self._is_back(holder.table_id, holder.account_id):
            await self._hold.lapse(holder.table_id, holder.account_id)
        self.wake_table(holder.table_id)

    async def _is_back(self, table_id: str, account_id: str) -> bool:
        """Whether the account is here at the table; an unreadable roster says no, which stores a leave the freeing
        reads the roster against again.
        """
        return self._is_here(account_id, await self._connected_or_none(table_id))

    def _is_here(self, account_id: str, connected: frozenset[str]) -> bool:
        """Whether the account counts as here at a table whose streams on every pod are `connected`: it streams there,
        or a lease of it runs here.
        """
        return account_id in connected or account_id in self.live_leases()

    def live_leases(self) -> frozenset[str]:
        """The agents whose lease runs: a read with no side effect, which a worker may call under a table's lock."""
        with self._state:
            return frozenset(self._lease_ends)

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

        A lapse wakes the streams, stores the chair's leave and, where no stream is open, a fresh wait for the empty
        table; a start wakes them and asks for the next deal. A failed read is retried while the lease still is in
        the state that was acted on.
        """
        if self._stopped or (account_id in self._lease_ends) == lapsed:
            return
        run = self._timer_runs.start(PresenceTimer.LEASE_SETTLE, account_id)
        try:
            table_ids = list(await self._lease.seated_tables(account_id))
        except Exception as failure:
            run.failed(failure)
            self._hold.scheduler.schedule(
                CHAIR_RELEASE_RETRY_SECONDS, partial(self._settle_lease, account_id, lapsed=lapsed)
            )
            return
        run.succeeded()
        for table_id in table_ids:
            self.wake_table(table_id)
            self._note_soon(table_id)
            if not lapsed:
                self.deal_soon(table_id)
                continue
            await self._store_leave(table_id, account_id, lapsed=True)
            if table_id not in self._subscriptions:
                self._start_empty_wait(table_id)

    async def subscribe(self, table_id: str, account_id: str, wake: Callable[[], None]) -> Subscription:
        """Register before the stream reads its view, so a change after this call wakes it.

        The stream's lease starts before the account's hold is cleared, the first stream's note and the arrival's wake,
        so each of them reads the roster with this stream in it; a lease that cannot start fails the arrival. The clear
        waits for a freeing of the chair in flight, so the first view shows what it did; a clear that fails is logged
        and fails nothing, since the freeing reads this stream in the roster and keeps the chair.
        """
        registration = self._wakes.register([TableTopic(table_id)], wake)
        lease = AsyncExitStack()
        try:
            already_connected = account_id in await self._connected_or_none(table_id)
            holder = StreamHolder(table_id, account_id, uuid.uuid4().hex)
            await lease.enter_async_context(self._stream_leases.kept(holder.encoded(), every=STREAM_RENEWAL_EVERY))
        except BaseException:
            self._wakes.unregister(registration)
            raise
        subscription = Subscription(holder, registration, lease)
        with self._state:
            self._empty_waits.pop(table_id, None)
            self._subscriptions.setdefault(table_id, []).append(subscription)
            first = len(self._subscriptions[table_id]) == 1
        try:
            await self._clear_hold(table_id, account_id)
            ended = first and await self._empty_table.note(
                table_id, self._connected_while_writing(table_id, asyncio.get_running_loop())
            )
        except BaseException:
            await self.close(subscription)
            if table_id in self._subscriptions:
                self._note_soon(table_id)
            raise
        if ended:
            self.table_ended(table_id)
        if not already_connected:
            self._wakes.wake(TableTopic(table_id), sparing=registration)
        return subscription

    async def _clear_hold(self, table_id: str, account_id: str) -> None:
        run = self._timer_runs.start(PresenceTimer.HOLD_CLEAR, table_id, account_id, table_id=table_id)
        try:
            await self._hold.clear(table_id, account_id)
        except Exception as failure:
            run.failed(failure)
        else:
            run.succeeded()

    async def _connected_or_none(self, table_id: str) -> frozenset[str]:
        """Who streams at the table, or nobody when the roster cannot be read: the arrival then wakes the others, which
        costs a read and shows nothing wrong.
        """
        try:
            return await self.connected(table_id)
        except Exception as failure:
            log.warning("presence_roster_read.failed", error_type=type(failure).__name__)
            return frozenset()

    def unsubscribe(self, subscription: Subscription) -> bool:
        """Drop the stream's registration and its place in this process at once; true when it was still there.
        `close` follows it with everything that awaits.
        """
        remaining = self._subscriptions.get(subscription.table_id, [])
        if subscription not in remaining:
            return False
        self._wakes.unregister(subscription.registration)
        with self._state:
            remaining.remove(subscription)
            if not remaining:
                del self._subscriptions[subscription.table_id]
        return True

    async def close(self, subscription: Subscription) -> None:
        """End a stream: drop it here at once, then run to the end, even when the caller is cancelled, what awaits.

        When it was the account's last stream at the table on any pod, its leave is stored while its lease still
        counts it, so the hold is stored before the absence starts, and the table's streams are woken once the lease
        has ended.
        """
        if self.unsubscribe(subscription):
            await _finished_despite_cancellation(self._finish_close(subscription))

    async def _finish_close(self, subscription: Subscription) -> None:
        table_id, account_id = subscription.table_id, subscription.account_id
        left = not any(each.account_id == account_id for each in self._subscriptions.get(table_id, []))
        if left and not await self._streams_elsewhere(subscription.holder):
            await self._store_leave(table_id, account_id, lapsed=False)
        try:
            await subscription.lease.aclose()
        except Exception as failure:
            # The failure's message may carry the account id, so only its type is logged.
            log.error("stream_close.failed", table_id=table_id, error_type=type(failure).__name__)
        if left:
            self.wake_table(table_id)
        if table_id not in self._subscriptions:
            self._start_empty_wait(table_id)
            self._note_soon(table_id)

    async def _streams_elsewhere(self, holder: StreamHolder) -> bool:
        """Whether another stream of the account watches the table on any pod, so that its leave waits for the last
        one; an unreadable roster says no, which stores the leave the freeing reads the roster against again.
        """
        try:
            present = Present.of(await self._stream_leases.live(), apart_from=holder)
        except Exception as failure:
            log.warning("presence_roster_read.failed", error_type=type(failure).__name__)
            return False
        return holder.account_id in present.at(holder.table_id)

    async def _store_leave(self, table_id: str, account_id: str, *, lapsed: bool) -> None:
        """Store the account's leave, as a lapse where its lease lapsed; a failure is logged and the leave stored again
        later while the presence runs.
        """
        run = self._timer_runs.start(PresenceTimer.LEAVE_WRITE, table_id, account_id, table_id=table_id)
        try:
            await (self._hold.lapse if lapsed else self._hold.leave)(table_id, account_id)
        except Exception as failure:
            run.failed(failure)
            if not self._stopped:
                self._hold.scheduler.schedule(
                    CHAIR_RELEASE_RETRY_SECONDS, partial(self._store_leave_again, table_id, account_id, lapsed=lapsed)
                )
            return
        run.succeeded()

    async def _store_leave_again(self, table_id: str, account_id: str, *, lapsed: bool) -> None:
        if not await self._is_back(table_id, account_id):
            await self._store_leave(table_id, account_id, lapsed=lapsed)

    def start_hold_sweeps(self) -> None:
        """Free the chairs whose hold is due every `HOLD_SWEEP_EVERY_SECONDS` while the presence runs."""
        self._hold.scheduler.schedule(HOLD_SWEEP_EVERY_SECONDS, self._sweep_holds)

    async def _sweep_holds(self) -> None:
        try:
            await self._free_due_holds()
        finally:
            if not self._stopped:
                self._hold.scheduler.schedule(HOLD_SWEEP_EVERY_SECONDS, self._sweep_holds)

    async def _free_due_holds(self) -> None:
        """Free each due hold's chair; an unknown presence ends the sweep, since it is unknown for every hold."""
        run = self._timer_runs.start(PresenceTimer.HOLD_SWEEP)
        try:
            due = list(await self._hold.due())
        except Exception as failure:
            run.failed(failure)
            return
        run.succeeded()
        loop = asyncio.get_running_loop()
        for table_id, account_id in due:
            run = self._timer_runs.start(PresenceTimer.CHAIR_RELEASE, table_id, account_id, table_id=table_id)
            try:
                freed = await self._hold.free_chair(
                    table_id, account_id, self._absent_while_freeing(table_id, account_id, loop)
                )
            except PresenceUnknownError as failure:
                run.failed(failure)
                return
            except Exception as failure:
                run.failed(failure)
                continue
            run.succeeded()
            if freed:
                self.wake_table(table_id)

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

        A failure of any kind, not only a failed roster read, is logged and the deal is asked for again after
        `CHAIR_RELEASE_RETRY_SECONDS` while the presence runs, as `_note_presence` and `_end_if_empty` do.
        """
        run = self._timer_runs.start(PresenceTimer.NEXT_DEAL, table_id, table_id=table_id)
        try:
            dealt = await self._next_deal.deal(
                table_id,
                self._connected_while_writing(table_id, asyncio.get_running_loop(), absence_decides=False),
            )
        except Exception as failure:
            run.failed(failure)
            if not self._stopped:
                self._hold.scheduler.schedule(CHAIR_RELEASE_RETRY_SECONDS, partial(self.deal_now, table_id))
            return
        run.succeeded()
        if dealt:
            self.wake_table(table_id)

    def watch_end_answers(self, table_id: str, seconds_left: float) -> None:
        """Ask once `seconds_left` have passed whether the table's proposal to end the series has lapsed; the step
        re-reads the table, so a timer for a proposal that is gone, answered or replaced does nothing. A table with a
        timer waiting that falls due no later gets no second one, while a deadline found earlier than the waiting
        timer's, a later yes having timed a full minute, gets its own, so the minute the store holds is the minute kept.
        """
        due = self._hold.clock() + seconds_left
        if self._stopped or self._end_answer_dues.get(table_id, math.inf) <= due:
            return
        self._end_answer_dues[table_id] = due
        self._hold.scheduler.schedule(seconds_left, partial(self._lapse_end_answers, table_id, due))

    def watch_all_end_answers(self, seconds_left_by_table: Mapping[str, float]) -> None:
        """Start the minute of each live table's standing proposal found in the store, at the server's start and again
        while it serves, which recovers the proposals whose timer ran on a pod that is gone.
        """
        for table_id, seconds_left in seconds_left_by_table.items():
            self.watch_end_answers(table_id, seconds_left)

    async def _lapse_end_answers(self, table_id: str, due: float) -> None:
        if self._end_answer_dues.get(table_id) == due:
            del self._end_answer_dues[table_id]
        run = self._timer_runs.start(PresenceTimer.END_ANSWER_LAPSE, table_id, table_id=table_id)
        try:
            left = await self._end_answers.lapse(table_id)
        except Exception as failure:
            run.failed(failure)
            self.watch_end_answers(table_id, CHAIR_RELEASE_RETRY_SECONDS)
            return
        run.succeeded()
        self.wake_table(table_id)
        if left is not None:
            self.watch_end_answers(table_id, left)

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
        run = self._timer_runs.start(PresenceTimer.EMPTY_SINCE_WRITE, table_id, table_id=table_id)
        try:
            ended = await self._empty_table.note(
                table_id, self._connected_while_writing(table_id, asyncio.get_running_loop())
            )
        except Exception as failure:
            run.failed(failure)
            self._note_soon(table_id, CHAIR_RELEASE_RETRY_SECONDS)
            return
        run.succeeded()
        if ended:
            self.table_ended(table_id)

    async def _end_if_empty(self, table_id: str, wait: object) -> None:
        if not self._is_latest_wait(table_id, wait):
            return
        loop = asyncio.get_running_loop()
        run = self._timer_runs.start(PresenceTimer.EMPTY_TABLE_END, table_id, table_id=table_id)
        try:
            ended = await self._empty_table.end(
                table_id, self._connected_while_writing(table_id, loop, partial(self._is_latest_wait, table_id, wait))
            )
        except Exception as failure:
            run.failed(failure)
            self._hold.scheduler.schedule(CHAIR_RELEASE_RETRY_SECONDS, partial(self._end_if_empty, table_id, wait))
            return
        run.succeeded()
        with self._state:
            if self._empty_waits.get(table_id) is wait:
                del self._empty_waits[table_id]
        if ended:
            self.table_ended(table_id)

    def table_ended(self, table_id: str) -> None:
        """Drop the table's ask clock entry and reactions and wake its streams; call it once the table's end is
        committed.
        """
        self.waits.drop(table_id)
        self.reactions.drop(table_id)
        self.wake_table(table_id)

    def _is_latest_wait(self, table_id: str, wait: object) -> bool:
        return not self._stopped and self._empty_waits.get(table_id) is wait

    def _absent_while_freeing(
        self, table_id: str, account_id: str, loop: asyncio.AbstractEventLoop
    ) -> AbstractContextManager[bool | None]:
        """Enter on a worker once it holds the table and the hold: yields whether the account is gone, and None once
        stopped. The account is gone when, by the roster, it is not here (`_is_here`).
        A roster that cannot be read, or that is unsettled and does not list the account, raises
        `PresenceUnknownError`, which frees nothing. The exit runs on the worker after the commit, so `finish_writes`
        outlives a cancelled event-loop task.
        """

        def connected_unless_unknown() -> frozenset[str] | None:
            present = self._present_from_worker(loop)
            if present is None:
                return None
            if not (account_id in present.at(table_id) or present.settled):
                raise PresenceUnknownError
            return present.at(table_id)

        return _absent_from(self._guarded_write(loop, connected_unless_unknown), partial(self._is_here, account_id))

    def _connected_while_writing(
        self,
        table_id: str,
        loop: asyncio.AbstractEventLoop,
        is_due: Callable[[], bool] = lambda: True,
        *,
        absence_decides: bool = True,
    ) -> AbstractContextManager[frozenset[str] | None]:
        """Enter on a worker once it holds the table: yields who is connected then, and None once stopped or when
        `is_due` says the caller's request has been superseded.

        The roster is read before `_state` is taken. A roster that cannot be read raises `PresenceUnknownError`, and
        so does an unsettled one that lists nobody at the table when `absence_decides`, which a write that ends or
        stamps an empty table sets and a deal does not. The exit runs on the worker after the commit, so
        `finish_writes` outlives a cancelled event-loop task.
        """

        def connected_at_the_table() -> frozenset[str] | None:
            present = self._present_from_worker(loop)
            if present is None:
                return None
            if absence_decides and not (present.at(table_id) or present.settled):
                raise PresenceUnknownError
            return present.at(table_id)

        return self._guarded_write(loop, connected_at_the_table, is_due)

    @contextmanager
    def _guarded_write(
        self,
        loop: asyncio.AbstractEventLoop,
        read_connected: Callable[[], frozenset[str] | None],
        is_due: Callable[[], bool] = lambda: True,
    ) -> Generator[frozenset[str] | None]:
        committing = asyncio.Event()
        connected_before = None
        if is_due():
            connected_before = read_connected()
        with self._state:
            due = connected_before is not None and not self._stopped and is_due()
            connected = connected_before if due else None
            if due:
                self._writing.add(committing)
        try:
            yield connected
        finally:
            if due:
                with self._state:
                    self._writing.discard(committing)
                loop.call_soon_threadsafe(committing.set)

    def _present_from_worker(self, loop: asyncio.AbstractEventLoop) -> Present | None:
        """Read the roster from a worker that holds a table's row lock, on the event loop that owns the client, and
        give up after `ROSTER_READ_TIMEOUT_SECONDS`: a read that fails or stalls is an unknown presence. The answer is
        None once the presence has stopped, which cancels a read in flight: its loop may end before it answers.
        """
        with self._state:
            if self._stopped:
                return None
            reading = asyncio.run_coroutine_threadsafe(self._read_present(), loop)
            self._reads.add(reading)
        try:
            return reading.result(ROSTER_READ_TIMEOUT_SECONDS)
        except CancelledError:
            return None
        except Exception as failure:
            reading.cancel()
            raise PresenceUnknownError from failure
        finally:
            with self._state:
                self._reads.discard(reading)

    async def finish_writes(self) -> None:
        """Wait until every freeing, deal or end that read its accounts has ended its transaction; call it after
        `stop`.
        """
        with self._state:
            writing = list(self._writing)
        for committing in writing:
            await committing.wait()


@contextmanager
def _absent_from(
    connected: AbstractContextManager[frozenset[str] | None], is_here: Callable[[frozenset[str]], bool]
) -> Generator[bool | None]:
    with connected as accounts:
        yield None if accounts is None else not is_here(accounts)
