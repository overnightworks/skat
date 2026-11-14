import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from skat.table.member_place import BookEntry
    from skat.table.records import EndedTable, Ending, Receipt, Replay, TableId, TableRecord
    from skat.table.transactions import LiveWait, OccupiedChair, PausedFacts, TableTransaction, TableTransactions


BARRIER_TIMEOUT_SECONDS = 0.5
WAIT_DEADLINE_SECONDS = 10
HANG_DEADLINE_SECONDS = 120


class FaultyTableTransactions:
    """A transaction port that delegates to a real one and injects one fault through the port itself.

    `blind_first_replay` makes the first replay lookup find nothing, as when a rival request has not
    committed yet; `receipt_failure` is raised when a receipt is added;
    `save_failure` is raised after a table is saved; `end_failure` is raised after a table is ended.
    """

    def __init__(
        self,
        inner: TableTransactions,
        *,
        blind_first_replay: bool = False,
        receipt_failure: Exception | None = None,
        save_failure: Exception | None = None,
        end_failure: Exception | None = None,
    ) -> None:
        self._inner = inner
        self._blind_replays_left = 1 if blind_first_replay else 0
        self._receipt_failure = receipt_failure
        self._save_failure = save_failure
        self._end_failure = end_failure

    @contextmanager
    def begin(self) -> Iterator[_FaultyTransaction]:
        with self._inner.begin() as transaction:
            yield _FaultyTransaction(transaction, self)

    def take_blind_replay(self) -> bool:
        blind = self._blind_replays_left > 0
        self._blind_replays_left -= blind
        return blind

    @property
    def save_failure(self) -> Exception | None:
        return self._save_failure

    @property
    def end_failure(self) -> Exception | None:
        return self._end_failure

    @property
    def receipt_failure(self) -> Exception | None:
        return self._receipt_failure


class _FaultyTransaction:
    def __init__(self, inner: TableTransaction, faults: FaultyTableTransactions) -> None:
        self._inner = inner
        self._faults = faults

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        if self._faults.take_blind_replay():
            return None
        return self._inner.replay(account_id, command_id)

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None:
        return self._inner.table(table_id)

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        return self._inner.locked_table(table_id)

    def save_table(self, table: TableRecord, *, played_at: datetime | None) -> None:
        self._inner.save_table(table, played_at=played_at)
        if self._faults.save_failure is not None:
            raise self._faults.save_failure

    def add_table(self, table: TableRecord, opener_name: str) -> None:
        self._inner.add_table(table, opener_name)

    def end_table(self, table_id: TableId, at: datetime, ending: Ending) -> None:
        self._inner.end_table(table_id, at, ending)
        if self._faults.end_failure is not None:
            raise self._faults.end_failure

    def opener_account(self, table_id: TableId) -> str | None:
        return self._inner.opener_account(table_id)

    def played_before(self, cutoff: datetime) -> tuple[TableId, ...]:
        return self._inner.played_before(cutoff)

    def empty_since(self, table_id: TableId) -> datetime | None:
        return self._inner.empty_since(table_id)

    def paused_facts(self, table_id: TableId) -> PausedFacts:
        return self._inner.paused_facts(table_id)

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        self._inner.set_empty_since(table_id, since)

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        return self._inner.live_empty_since()

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        return self._inner.occupied_chairs()

    def locked_book_entry(self, table_id: TableId, agent_account: str) -> BookEntry | None:
        return self._inner.locked_book_entry(table_id, agent_account)

    def locked_book_entries_of(self, agent_account: str) -> tuple[BookEntry, ...]:
        return self._inner.locked_book_entries_of(agent_account)

    def save_book_entry(self, entry: BookEntry) -> None:
        self._inner.save_book_entry(entry)

    def book_accounts_at(self, table_id: TableId) -> frozenset[str]:
        return self._inner.book_accounts_at(table_id)

    def add_receipt(self, receipt: Receipt) -> None:
        if self._faults.receipt_failure is not None:
            raise self._faults.receipt_failure
        self._inner.add_receipt(receipt)


class BothReadBeforeEitherWrites:
    """Holds each command after its locking read until its rival has read too, if the rival can.

    Without a row lock both rivals read the free chair and both would write; with it the second waits
    outside, the barrier breaks after its timeout and the first goes on alone. With `rivals_must_meet=True` a broken
    barrier raises instead, so a test that needs both reads at once fails when a lock keeps them apart.
    """

    def __init__(self, inner, rivals, *, rivals_must_meet=False):
        self._inner = inner
        self._rivals_must_meet = rivals_must_meet
        timeout = WAIT_DEADLINE_SECONDS if rivals_must_meet else BARRIER_TIMEOUT_SECONDS
        self._barrier = threading.Barrier(rivals, timeout=timeout)

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            yield _WaitingTransaction(transaction, self._barrier, self._rivals_must_meet)


class _WaitingTransaction:
    def __init__(self, inner, barrier, rivals_must_meet):
        self._inner = inner
        self._barrier = barrier
        self._rivals_must_meet = rivals_must_meet

    def locked_table(self, table_id):
        table = self._inner.locked_table(table_id)
        if self._rivals_must_meet:
            self._barrier.wait()
        else:
            with suppress(threading.BrokenBarrierError):
                self._barrier.wait()
        return table

    def __getattr__(self, name):
        return getattr(self._inner, name)


class HoldsTheRowLock:
    """Holds each command after its decision is saved, with its row lock and open transaction, until `release` is set.

    `held` is set once the command stands there, so a test reads other tables and waits behind this one's row.
    """

    def __init__(self, inner):
        self._inner = inner
        self.held = threading.Event()
        self.release = threading.Event()

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            yield _HoldingTransaction(transaction, self)


class _HoldingTransaction:
    def __init__(self, inner, holder):
        self._inner = inner
        self._holder = holder

    def save_table(self, table, *, played_at):
        self._inner.save_table(table, played_at=played_at)
        self._holder.held.set()
        assert self._holder.release.wait(WAIT_DEADLINE_SECONDS), "the held command was never released"

    def __getattr__(self, name):
        return getattr(self._inner, name)
