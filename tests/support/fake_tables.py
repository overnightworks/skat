import copy
import math
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skat.table.records import Chair, EndedTable, Ending, Receipt, Replay, TableId, TableRecord, Visibility
from skat.table.rules import CREATE_TABLE_COMMAND, played_series_of
from skat.table.series_end import series_asked_at
from skat.table.service import TableService
from skat.table.transactions import (
    DuplicateReceiptError,
    HeldChair,
    LiveAsk,
    LiveWait,
    OccupiedChair,
    PausedFacts,
    TableVersion,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from skat.table.game_cards import GameCards
    from skat.table.member_place import BookEntry


class FreeChairReadyError(Exception):
    """The store's check refuses a free chair that is ready."""


class DealtWithoutTimeError(Exception):
    """The store's check refuses a dealt table that holds no last played time."""


class FakeTableStore:
    """The transaction port in memory: a block that raises leaves the store as it found it.

    `clock` is the store's own clock, on which a chair hold falls due.
    """

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.clock = clock
        self.holds: dict[tuple[str, str], datetime] = {}
        self.tables: dict[str, TableRecord | EndedTable] = {}
        self.receipts: dict[tuple[str, str], Receipt] = {}
        self.ended_at: dict[str, datetime] = {}
        self.with_games: set[str] = set()
        self.empty_since_by_table: dict[str, datetime | None] = {}
        self.last_played_at: dict[str, datetime] = {}
        self.opener_names: dict[str, str] = {}
        self.book: dict[tuple[str, str], BookEntry] = {}

    @contextmanager
    def begin(self) -> Iterator[FakeTableStore]:
        before = copy.deepcopy(
            (
                self.tables,
                self.receipts,
                self.ended_at,
                self.with_games,
                self.empty_since_by_table,
                self.last_played_at,
                self.opener_names,
                self.book,
                self.holds,
            )
        )
        try:
            yield self
        except BaseException:
            (
                self.tables,
                self.receipts,
                self.ended_at,
                self.with_games,
                self.empty_since_by_table,
                self.last_played_at,
                self.opener_names,
                self.book,
                self.holds,
            ) = before
            raise

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        receipt = self.receipts.get((account_id, command_id))
        if receipt is None:
            return None
        return Replay(
            receipt.command, receipt.payload, self.tables[receipt.table_id.value], receipt.refusal, receipt.holder
        )

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None:
        return self.tables.get(table_id.value)

    def game_cards(self, table_id: TableId, series_number: int, number: int) -> GameCards | None:
        table = self.table(table_id)
        played = None if table is None else played_series_of(table)
        if played is None or played.number != series_number or not 1 <= number <= len(played.game_list):
            return None
        return played.game_list[number - 1].cards

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        table = self.table(table_id)
        return table if isinstance(table, TableRecord) else None

    def save_table(self, table: TableRecord, *, played_at: datetime | None) -> None:
        if any(chair.ready and chair.occupant is None for chair in table.chairs):
            message = f"table {table.id.value} would keep a free chair ready"
            raise FreeChairReadyError(message)
        if played_at is not None:
            self.last_played_at[table.id.value] = played_at
        if table.dealer is not None and table.id.value not in self.last_played_at:
            message = f"table {table.id.value} is dealt and holds no last played time"
            raise DealtWithoutTimeError(message)
        self.tables[table.id.value] = table

    def save_turn_state(self, table_id: TableId, chair: Chair) -> None:
        table = self.tables[table_id.value]
        assert isinstance(table, TableRecord)
        chairs = tuple(chair if each.seat == chair.seat else each for each in table.chairs)
        self.tables[table_id.value] = replace(table, chairs=chairs)

    def add_table(self, table: TableRecord, opener_name: str) -> None:
        self.tables[table.id.value] = table
        self.opener_names[table.id.value] = opener_name

    def played_before(self, cutoff: datetime) -> tuple[TableId, ...]:
        return tuple(
            TableId(table_id)
            for table_id, played_at in sorted(self.last_played_at.items())
            if played_at <= cutoff and isinstance(self.tables[table_id], TableRecord)
        )

    def end_table(self, table_id: TableId, at: datetime, ending: Ending) -> None:
        table = self.tables[table_id.value]
        last_series = played_series_of(table) if table.game_list else None
        self.tables[table_id.value] = EndedTable(table.id, table.version + 1, ending, last_series)
        self.ended_at[table_id.value] = at
        if table.game_list:
            self.with_games.add(table_id.value)
        self.last_played_at.pop(table_id.value, None)
        self.opener_names.pop(table_id.value, None)
        self.book = {key: entry for key, entry in self.book.items() if entry.table_id != table_id}
        self.receipts = {
            key: receipt
            for key, receipt in self.receipts.items()
            if receipt.table_id != table_id or receipt.command == CREATE_TABLE_COMMAND
        }

    def forget_ended_before(self, cutoff: datetime) -> int:
        due = {table_id for table_id, at in self.ended_at.items() if at <= cutoff}
        deleted = len(due - self.with_games)
        for table_id in due - self.with_games:
            del self.tables[table_id], self.ended_at[table_id]
            self.receipts = {
                key: receipt for key, receipt in self.receipts.items() if receipt.table_id.value != table_id
            }
            self.holds = {key: due for key, due in self.holds.items() if key[0] != table_id}
        for table_id in due & self.with_games:
            ended = self.tables[table_id]
            self.tables[table_id] = replace(ended, ending=replace(ended.ending, closed_by_name=None))
        return deleted

    def empty_since(self, table_id: TableId) -> datetime | None:
        return self.empty_since_by_table.get(table_id.value)

    def paused_facts(self, table_id: TableId) -> PausedFacts:
        return PausedFacts(self.last_played_at.get(table_id.value), self.opener_names.get(table_id.value))

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        self.empty_since_by_table[table_id.value] = since

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        return tuple(
            LiveWait(table.id, table.dealer, self.empty_since_by_table.get(table.id.value))
            for table in self.tables.values()
            if isinstance(table, TableRecord)
        )

    def live_end_asks(self) -> tuple[LiveAsk, ...]:
        return tuple(
            LiveAsk(table.id, asked_at)
            for table in self.tables.values()
            if isinstance(table, TableRecord) and table.series is not None
            if (asked_at := series_asked_at(table.series)) is not None
        )

    def hold_due(self, table_id: str, account_id: str) -> None:
        """Store a hold of the account's chair whose deadline has passed, as a scenario's arrangement."""
        self.holds[table_id, account_id] = self.clock() - timedelta(seconds=1)

    def store_leave(self, table_id: TableId, account_id: str, hold_seconds: float, *, newest_wins: bool) -> None:
        if (newest_wins or (table_id.value, account_id) not in self.holds) and any(
            chair.table_id == table_id and chair.account_id == account_id for chair in self._occupied_chairs()
        ):
            self.holds[table_id.value, account_id] = self.clock() + timedelta(seconds=hold_seconds)

    def delete_hold(self, table_id: TableId, account_id: str) -> None:
        self.holds.pop((table_id.value, account_id), None)

    def locked_hold_due(self, table_id: TableId, account_id: str) -> bool:
        due_at = self.holds.get((table_id.value, account_id))
        return due_at is not None and due_at <= self.clock()

    def due_holds(self, limit: int) -> tuple[HeldChair, ...]:
        now = self.clock()
        due = sorted((due_at, key) for key, due_at in self.holds.items() if due_at <= now)
        return tuple(HeldChair(TableId(table_id), account_id) for _, (table_id, account_id) in due[:limit])

    def hold_seconds_left(self, table_id: TableId) -> dict[str, int]:
        now = self.clock()
        return {
            account_id: max(0, math.ceil((due_at - now).total_seconds()))
            for (at_table, account_id), due_at in self.holds.items()
            if at_table == table_id.value
        }

    def _occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        return tuple(
            OccupiedChair(table.id, chair.occupant.account_id)
            for table in self.tables.values()
            if isinstance(table, TableRecord)
            for chair in table.chairs
            if chair.occupant is not None
        )

    @staticmethod
    def _version_of(table: TableRecord) -> TableVersion:
        stated = tuple(chair.turn_state.stated_at for chair in table.chairs if chair.turn_state is not None)
        return TableVersion(table.id, table.version, stated)

    def tables_of(self, account_id: str) -> tuple[TableVersion, ...]:
        return tuple(
            self._version_of(table)
            for table in sorted(self.tables.values(), key=lambda each: each.id.value)
            if isinstance(table, TableRecord)
            if any(chair.occupant is not None and chair.occupant.account_id == account_id for chair in table.chairs)
        )

    def open_table_ids(self) -> tuple[TableId, ...]:
        return tuple(
            table.id
            for table in sorted(self.tables.values(), key=lambda each: each.id.value)
            if isinstance(table, TableRecord) and table.visibility is Visibility.OPEN
        )

    def versions_of(self, table_ids: Iterable[TableId]) -> tuple[TableVersion, ...]:
        wanted = {table_id.value for table_id in table_ids}
        return tuple(
            self._version_of(table)
            for table in sorted(self.tables.values(), key=lambda each: each.id.value)
            if isinstance(table, TableRecord) and table.id.value in wanted
        )

    def chairs_taken_by(self, table_ids: Iterable[TableId], account_ids: frozenset[str]) -> frozenset[OccupiedChair]:
        wanted = {table_id.value for table_id in table_ids}
        return frozenset(
            chair
            for chair in self._occupied_chairs()
            if chair.table_id.value in wanted and chair.account_id in account_ids
        )

    def locked_book_entry(self, table_id: TableId, agent_account: str) -> BookEntry | None:
        return self.book.get((table_id.value, agent_account))

    def locked_book_entries_of(self, agent_account: str) -> tuple[BookEntry, ...]:
        return tuple(entry for (_, account), entry in sorted(self.book.items()) if account == agent_account)

    def save_book_entry(self, entry: BookEntry) -> None:
        self.book[entry.table_id.value, entry.agent_account] = entry

    def book_accounts_at(self, table_id: TableId) -> frozenset[str]:
        return frozenset(account for (at_table, account) in self.book if at_table == table_id.value)

    def add_receipt(self, receipt: Receipt) -> None:
        key = (receipt.account_id, receipt.command_id)
        if key in self.receipts:
            raise DuplicateReceiptError
        self.receipts[key] = receipt


def in_memory_tables() -> TableService:
    return TableService(FakeTableStore())
