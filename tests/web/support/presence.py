import asyncio
from contextlib import contextmanager

from logline import Outcome
from tandem import Lapse
from tandem.deadlines import Due

from skat.table.server_steps import EndAnswerLapse
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.presence import ChairHold, EmptyTable, NextDeal, Presence
from skat.web.presence_line import EVENT
from skat.web.stream_holder import StreamHolder
from skat.web.tables import TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.idle_presence import idle_agent_lease, idle_end_answers, idle_wakes, note_nothing
from tests.support.in_memory_leases import InMemoryLeases
from tests.support.log_lines import lines_of
from tests.support.played_game import after_the_first_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

TABLE = "t" * 32
OTHER_TABLE = "o" * 32
HOLD_SECONDS = 300
FAILURE_NAMING_AN_ACCOUNT = "account anna"
THIRD_PASS_COMMAND = "pass-seat-3"


def failed_timers(lines):
    """The timer and level of each line a failed run of a presence timer wrote."""
    return [(line["timer"], line["level"]) for line in lines_of(lines, EVENT) if line["outcome"] == Outcome.FAILED]


def view_of_version(messages, version):
    return next(view for view in messages if view["version"] >= version)


class Wakes:
    """What each subscriber was told: one counter per name."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def callback(self, name):
        self.counts.setdefault(name, 0)

        def wake():
            self.counts[name] += 1

        return wake


async def on_a_worker(guard, work, within=None):
    """What a table command does in its worker: enter `guard` there, call `work` with what it yields and, while the
    guard is held, wait for `within`, which runs on the event loop.
    """
    loop = asyncio.get_running_loop()

    def enter():
        with guard as yielded:
            outcome = work(yielded)
            if within is not None:
                asyncio.run_coroutine_threadsafe(within(), loop).result(5)
        return outcome

    return await asyncio.to_thread(enter)


class Holds:
    """The stored chair holds as the presence uses them: the leaves stored, the lapses stored and the holds cleared,
    each in order, the holds the store answers as due, each freeing asked for with what its guard yielded, and the
    failures to come.

    `on_leave` and `on_clear` run inside the write, before it answers.
    """

    def __init__(self):
        self.left = []
        self.lapsed = []
        self.cleared = []
        self.due_now = []
        self.calls = []
        self.outcomes = []
        self.leave_failures = []
        self.clear_failures = []
        self.due_failures = []
        self.free_failures = []
        self.on_leave = None
        self.on_clear = None

    async def leave(self, table_id, account_id):
        if self.leave_failures:
            raise self.leave_failures.pop(0)
        if self.on_leave is not None:
            await self.on_leave()
        self.left.append((table_id, account_id))

    async def lapse(self, table_id, account_id):
        if self.leave_failures:
            raise self.leave_failures.pop(0)
        self.lapsed.append((table_id, account_id))

    async def clear(self, table_id, account_id):
        if self.clear_failures:
            raise self.clear_failures.pop(0)
        if self.on_clear is not None:
            await self.on_clear()
        self.cleared.append((table_id, account_id))

    async def due(self):
        if self.due_failures:
            raise self.due_failures.pop(0)
        return list(self.due_now)

    async def free_chair(self, table_id, account_id, absent):
        self.calls.append((table_id, account_id))
        if self.free_failures:
            raise self.free_failures.pop(0)
        yielded = await on_a_worker(absent, lambda is_absent: is_absent)
        self.outcomes.append(yielded)
        if yielded is not None:
            self.due_now.remove((table_id, account_id))
        return bool(yielded)


def chair_hold(time, holds):
    """The chair hold of a presence on the test's time, over the fake store of holds."""
    return ChairHold(time.clock, time, holds.leave, holds.lapse, holds.clear, holds.due, holds.free_chair)


def presence_on(time, holds, deals, ends, *, note=note_nothing, lease=None, leases=None, end_answers=None):
    """A presence on the test's time over the fakes of the stores, idle where a part is not given."""
    return Presence(
        chair_hold(time, holds),
        deals.port(),
        EmptyTable(ends.end, note, ends.due),
        lease or idle_agent_lease(),
        idle_wakes(),
        leases or InMemoryLeases(),
        end_answers or idle_end_answers(),
    )


class Deals:
    """The deal commands as the presence calls them, with the pauses stored for them: what each was asked, the tables
    whose pause is over, and what the commands answer or raise next.
    """

    def __init__(self):
        self.calls = []
        self.paused = []
        self.deferred = []
        self.due_now = []
        self.failures = []
        self.due_failures = []
        self.write_failures = []
        self.dealt = True
        self.seated = frozenset()
        self.meanwhile = None

    def port(self):
        return NextDeal(self.deal_next, self.after_pause, self.pause, self.defer, self.due)

    async def deal_next(self, table_id, connected_accounts):
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            await self.meanwhile()
        await on_a_worker(connected_accounts, lambda connected: self.calls.append((table_id, connected)))
        return self.dealt

    async def after_pause(self, table_id, connected_accounts):
        """The pause step: it deals only when everyone seated is connected, and drops the pause once the presence
        answered; a presence that raises leaves it.
        """
        dealt = await self.deal_next(table_id, connected_accounts(self.seated))
        connected = self.calls[-1][1]
        if connected is not None and table_id in self.due_now:
            self.due_now.remove(table_id)
        return dealt and connected is not None and self.seated <= connected

    async def pause(self, table_id):
        if self.write_failures:
            raise self.write_failures.pop(0)
        self.paused.append(table_id)

    async def defer(self, table_id):
        if self.write_failures:
            raise self.write_failures.pop(0)
        self.deferred.append(table_id)

    async def due(self):
        if self.due_failures:
            raise self.due_failures.pop(0)
        return list(self.due_now)


class Lapses:
    """The step the presence asks: it raises what `failures` holds, then answers what `left` holds, then none."""

    def __init__(self):
        self.asked = []
        self.failures = []
        self.left = []

    async def lapse(self, table_id):
        self.asked.append(table_id)
        if self.failures:
            raise self.failures.pop(0)
        return EndAnswerLapse(self.left.pop(0) if self.left else None)


class Notes:
    """The note command as the presence calls it: who was connected when each write held the row."""

    def __init__(self):
        self.calls = []
        self.failures = []
        self.ended = False
        self.meanwhile = None

    async def note(self, table_id, connected_accounts):
        if self.meanwhile is not None:
            await self.meanwhile()
        if self.failures:
            raise self.failures.pop(0)
        await on_a_worker(connected_accounts, lambda connected: self.calls.append((table_id, connected)))
        return self.ended


# one asyncio.run, which the store tests' `run` also is; a one-line wrapper that no neutral support module is worth
def run(scenario):
    return asyncio.run(scenario)


def lapse_of(table_id, account_id):
    return Lapse(StreamHolder(table_id, account_id, "stream").encoded(), "generation", Due("key", "claim"))


async def serve_lapses(holding, leases):
    """Serve the lapses `leases` lists until each is handed, then stop serving."""
    serving = asyncio.create_task(holding.serve_lapses())
    await asyncio.wait_for(leases.lapses_handed.wait(), 5)
    serving.cancel()
    await asyncio.gather(serving, return_exceptions=True)


def stop_during_a_hanging_read(holding, leases, work):
    """Start the work, stop the presence once its roster read hangs, and wait for the work to end."""
    leases.reading_hangs = True

    async def scenario():
        working = asyncio.create_task(work())
        await leases.read_started.wait()
        holding.stop()
        await asyncio.wait_for(working, 5)

    run(scenario())


def connect(presence, table_id, account_id, wake):
    return run(presence.subscribe(table_id, account_id, wake))


def post_pass(skat, table_id, headers, *, command_id, version):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
        json={"command_id": command_id, "version": version},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def pass_hand_in(skat, table_id, people, seats_in_turn=(1, 2, 3)):
    """By default in `seated_three`'s turn: it dealt seat 1 the middlehand, seat 2 the rearhand, seat 3 the forehand."""
    for seat in seats_in_turn:
        version = skat.store.tables[table_id].version
        answer = post_pass(skat, table_id, people[seat - 1][0], command_id=f"pass-at-{version}", version=version)
        assert answer.status_code == 200, answer.text


def occupied_seats(skat, table_id):
    return {chair.seat for chair in skat.store.tables[table_id].chairs if chair.occupant is not None}


def end_the_first_game(store, table_id, *ready_seats):
    store.tables[table_id] = after_the_first_game(store.tables[table_id], *ready_seats)
    return store.tables[table_id]


class OvertakenStore(FakeTableStore):
    """A store another caller overtakes: `meanwhile` runs once when the next row lock is asked, `after_commit` once
    when the next transaction has committed, `after_commit_of_command` once when the transaction that recorded the
    receipt of the named command has committed, whatever other transactions commit before it."""

    def __init__(self):
        super().__init__()
        self.meanwhile = None
        self.after_commit = None
        self.after_commit_of_command = None
        self._command_recorded = False

    @contextmanager
    def begin(self):
        with super().begin() as transaction:
            yield transaction
        if self.after_commit is not None:
            action, self.after_commit = self.after_commit, None
            action()
        if self._command_recorded:
            self._command_recorded = False
            action, self.after_commit_of_command = self.after_commit_of_command[1], None
            action()

    def add_receipt(self, receipt):
        super().add_receipt(receipt)
        if self.after_commit_of_command is not None and receipt.command_id == self.after_commit_of_command[0]:
            self._command_recorded = True

    def locked_table(self, table_id):
        if self.meanwhile is not None:
            action, self.meanwhile = self.meanwhile, None
            action()
        return super().locked_table(table_id)
