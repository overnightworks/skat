"""The lobby's lists: the tables an account holds a chair at, projected from each table's member view, the paused ones
among them, and the open tables every member may sit down at.

An entry of the account's own list is built for one account from its own chairs, so no table reaches an account that
holds none there; its entries are ordered by what the account has to do, the tables that wait for it first. The list of
open tables names no card and no account and leaves out every private table and every table the account holds a chair
at, which its own list carries.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.table.awaiting import WaitingCase, waiting_case
from skat.table.member_view import member_view_of
from skat.table.records import OccupantKind, TableRecord, Visibility
from skat.table.rules import (
    hand_was_dealt,
    hold_frees_chair,
    present_at,
    seat_of,
    unplayed_end,
    waiting_seat_of,
)
from skat.table.views import paused_entry_of, turn_seat_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from datetime import datetime

    from skat.table.member_view import MemberView
    from skat.table.records import Actor, Chair, TableId, TableOptions
    from skat.table.transactions import OccupiedChair, PausedFacts, TableTransactions, TableVersion
    from skat.table.views import PausedEntryView

__all__ = [
    "LobbyChairView",
    "LobbyEntryView",
    "LobbyReads",
    "OpenChairView",
    "OpenEntryView",
]

# A Kontra word is a question in a running hand as the give-up is, so both share a rank.
_WAITING_RANK = {
    WaitingCase.TURN: 0,
    WaitingCase.GIVE_UP: 1,
    WaitingCase.KONTRA: 1,
    WaitingCase.END_PROPOSAL: 2,
    WaitingCase.RESULT: 3,
    WaitingCase.SERIES_END: 4,
}


@dataclass(frozen=True)
class LobbyChairView:
    """A chair of the account's table: who sits there and the facts the lobby draws; never a card."""

    seat: int
    occupant_name: str | None
    occupant_kind: OccupantKind | None
    is_mine: bool
    ready: bool
    total: int | None
    is_away: bool
    is_turn: bool
    hold_seconds_left: int | None


@dataclass(frozen=True)
class OpenChairView:
    """A chair of an open table: who sits there, whether they are away and how long their hold has left."""

    seat: int
    occupant_name: str | None
    occupant_kind: OccupantKind | None
    is_away: bool
    hold_seconds_left: int | None


@dataclass(frozen=True)
class OpenEntryView:
    """An open table as every member sees it in the lobby: the seated names in chair order, its free chairs (none for
    a full table), the series length and the rule options it is opened with, and how many accounts without a chair are
    connected.

    `title_name` is the name its opener had when he opened it; `game_number` and `game_count` are None for a table
    without a series. `dealt` says a hand was dealt and `waiting_seat` the chair the running hand waits for a sitter
    at; `ends_at` is set only when a hand was dealt and nobody is present. The entry names no card and no account.
    """

    id: str
    title_name: str | None
    game_number: int | None
    game_count: int | None
    options: TableOptions
    watchers: int
    free_chairs: int
    dealt: bool
    waiting_seat: int | None
    ends_at: datetime | None
    chairs: tuple[OpenChairView, ...]


@dataclass(frozen=True)
class LobbyEntryView:
    """A live table the account holds a chair at, with whether and why it waits for the account.

    `private` says the table is listed to its chair holders alone. `title_name` is the name its opener had when he
    opened it, None before the name was kept; `game_number` and `game_count` are None for a table without a series.
    `ends_at` is the instant the table ends, in UTC, and is set only when a hand was dealt and nobody is present.
    The entry names no card, no card count and no account.
    """

    id: str
    private: bool
    title_name: str | None
    game_number: int | None
    game_count: int | None
    dealt: bool
    awaits_you: bool
    waits_on: WaitingCase | None
    result_waits: bool
    series_over: bool
    ends_at: datetime | None
    chairs: tuple[LobbyChairView, ...]


class LobbyReads:
    """The reads behind the lobby's lists; the table service is built on them.

    A subclass sets the transactions and the live-lease read these reads use.
    """

    _transactions: TableTransactions
    _live_leases: Callable[[], frozenset[str]]

    def held_tables(self, account_id: str) -> tuple[TableVersion, ...]:
        """The tables the account holds a chair at, each once with its version, in id order; an unlocked read, so a
        candidate list.
        """
        with self._transactions.begin() as transaction:
            return transaction.tables_of(account_id)

    def tables_held_by(self, account_id: str) -> tuple[TableId, ...]:
        """The tables the account holds a chair at, each once, in id order; an unlocked read, so a candidate list."""
        return tuple(held.table_id for held in self.held_tables(account_id))

    def open_table_ids(self) -> tuple[TableId, ...]:
        """The live open tables, in id order; an unlocked read, so a candidate list."""
        with self._transactions.begin() as transaction:
            return transaction.open_table_ids()

    def table_versions(self, table_ids: Iterable[TableId]) -> tuple[TableVersion, ...]:
        """The version of each live table among `table_ids`, in id order; an unlocked read, which is how a caller asks
        cheaply whether a table it read before has changed.
        """
        with self._transactions.begin() as transaction:
            return transaction.versions_of(table_ids)

    def leased_seats(self, table_ids: Iterable[TableId]) -> frozenset[OccupiedChair]:
        """The chairs at `table_ids` whose occupant is an agent with a running lease, who counts as present there
        without a stream; an unlocked read, which is how a caller asks cheaply whether who is present at a table
        changed. Nothing is read while no lease runs.
        """
        leased = self._live_leases()
        if not leased:
            return frozenset()
        with self._transactions.begin() as transaction:
            return transaction.chairs_taken_by(table_ids, leased)

    def my_tables(
        self,
        account_id: str,
        held_ids: Iterable[TableId],
        connected_by_table: Mapping[str, frozenset[str]],
        hold_left_by_table: Mapping[str, Mapping[str, int]],
        days: int,
    ) -> tuple[LobbyEntryView, ...]:
        """The entries of the tables the account holds a chair at, in the lobby's order.

        `held_ids` is a candidate list from an unlocked read, so each table is read again in one transaction under its
        shared row lock: an ended table and a table whose chair the account left meanwhile are skipped. A table with
        nobody in `connected_by_table` has nobody connected; the agents whose lease runs count as present.
        `hold_left_by_table` gives the seconds each away member's hold has left, by table and account.
        """
        live_leases = self._live_leases()
        entries: list[LobbyEntryView] = []
        with self._transactions.begin() as transaction:
            for table_id in held_ids:
                table = transaction.table(table_id)
                if not isinstance(table, TableRecord):
                    continue
                present = present_at(table, connected_by_table.get(table_id.value, frozenset()), live_leases)
                member = member_view_of(table, account_id, present, transaction.opener_account(table_id))
                if member is not None:
                    holds = hold_left_by_table.get(table_id.value, {})
                    entries.append(_entry_of(table, member, present, holds, transaction.paused_facts(table_id), days))
        return tuple(sorted(entries, key=_order_of))

    def open_tables(
        self,
        account_id: str,
        listed_ids: Iterable[TableId],
        connected_by_table: Mapping[str, frozenset[str]],
        hold_left_by_table: Mapping[str, Mapping[str, int]],
        days: int,
    ) -> tuple[OpenEntryView, ...]:
        """The entries of the open tables the account holds no chair at, the fewest free chairs first, the full
        tables last and ties in id order.

        `listed_ids` is a candidate list from an unlocked read, so each table is read again in one transaction under
        its shared row lock: an ended table, a private one and a table whose chair the account took meanwhile are
        skipped. The other parameters are those of `my_tables`.
        """
        live_leases = self._live_leases()
        entries: list[OpenEntryView] = []
        with self._transactions.begin() as transaction:
            for table_id in listed_ids:
                table = transaction.table(table_id)
                if not isinstance(table, TableRecord) or table.visibility is not Visibility.OPEN:
                    continue
                if seat_of(table, account_id) is not None:
                    continue
                connected = connected_by_table.get(table_id.value, frozenset())
                present = present_at(table, connected, live_leases)
                holds = hold_left_by_table.get(table_id.value, {})
                facts = transaction.paused_facts(table_id)
                entries.append(_open_entry_of(table, connected, present, holds, facts, days))
        return tuple(sorted(entries, key=_open_order_of))

    def paused_tables(self, actor: Actor, days: int) -> tuple[PausedEntryView, ...]:
        """The live tables on which a hand was dealt and whose chair the actor holds, the soonest end first, ties in
        id order; a table ends `days` days after the time of its last deal or step of play.

        The held tables are a candidate list from an unlocked read, so each table is read again in one transaction
        under its shared row lock: an ended table, a table without a dealt hand and one whose chair the actor left
        meanwhile are skipped.
        """
        held_ids = self.tables_held_by(actor.account_id)
        with self._transactions.begin() as transaction:
            tables = (transaction.table(table_id) for table_id in held_ids)
            entries: list[PausedEntryView] = []
            for table in tables:
                if (
                    isinstance(table, TableRecord)
                    and hand_was_dealt(table)
                    and seat_of(table, actor.account_id) is not None
                ):
                    facts = transaction.paused_facts(table.id)
                    assert facts.last_played_at is not None  # noqa: S101 - narrows the type; a dealt table has its time
                    ends_at = unplayed_end(facts.last_played_at, days)
                    entries.append(paused_entry_of(table, actor.account_id, ends_at, facts.opener_name))
        return tuple(sorted(entries, key=lambda entry: (entry.ends_at, entry.id)))


def _entry_of(
    table: TableRecord,
    member: MemberView,
    present: frozenset[str],
    holds: Mapping[str, int],
    facts: PausedFacts,
    days: int,
) -> LobbyEntryView:
    view = member.view
    turn_seat = turn_seat_of(view.hand)
    return LobbyEntryView(
        id=view.id,
        private=table.visibility is Visibility.PRIVATE,
        title_name=facts.opener_name,
        game_number=None if view.series is None else view.series.game_number,
        game_count=None if view.series is None else view.series.game_count,
        dealt=hand_was_dealt(table),
        awaits_you=member.awaits_you,
        waits_on=waiting_case(view),
        result_waits=view.result is not None,
        series_over=view.series is not None and view.series.over,
        ends_at=_end_of(table, present, facts, days),
        chairs=tuple(
            LobbyChairView(
                seat=chair.seat,
                occupant_name=chair.occupant_name,
                occupant_kind=chair.occupant_kind,
                is_mine=chair.is_mine,
                ready=chair.ready,
                total=chair.total,
                is_away=chair.is_away,
                is_turn=chair.seat == turn_seat,
                hold_seconds_left=_hold_left_of(table.chairs[chair.seat - 1], table, present, holds),
            )
            for chair in view.chairs
        ),
    )


def _open_entry_of(
    table: TableRecord,
    connected: frozenset[str],
    present: frozenset[str],
    holds: Mapping[str, int],
    facts: PausedFacts,
    days: int,
) -> OpenEntryView:
    seated = {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}
    return OpenEntryView(
        id=table.id.value,
        title_name=facts.opener_name,
        game_number=None if table.series is None else table.series.deals,
        game_count=None if table.series is None else table.series.length,
        options=table.options,
        watchers=len(connected - seated),
        free_chairs=sum(chair.occupant is None for chair in table.chairs),
        dealt=hand_was_dealt(table),
        waiting_seat=waiting_seat_of(table),
        ends_at=_end_of(table, present, facts, days),
        chairs=tuple(
            OpenChairView(
                seat=chair.seat,
                occupant_name=None if chair.occupant is None else chair.occupant.display_name,
                occupant_kind=None if chair.occupant is None else chair.occupant.kind,
                is_away=chair.occupant is not None and chair.occupant.account_id not in present,
                hold_seconds_left=_hold_left_of(chair, table, present, holds),
            )
            for chair in table.chairs
        ),
    )


def _hold_left_of(chair: Chair, table: TableRecord, present: frozenset[str], holds: Mapping[str, int]) -> int | None:
    """The seconds the chair's hold has left: only an absent occupant's at a table whose hold may free its chairs."""
    if chair.occupant is None or chair.occupant.account_id in present or not hold_frees_chair(table):
        return None
    return holds.get(chair.occupant.account_id)


def _end_of(table: TableRecord, present: frozenset[str], facts: PausedFacts, days: int) -> datetime | None:
    if not hand_was_dealt(table) or present:
        return None
    assert facts.last_played_at is not None  # noqa: S101 - narrows the type; a dealt table has its time
    return unplayed_end(facts.last_played_at, days)


def _open_order_of(entry: OpenEntryView) -> tuple[bool, int, str]:
    """Sort key: the tables with a free chair, the fewest free chairs first, then the full ones, each group by id."""
    return entry.free_chairs == 0, entry.free_chairs, entry.id


def _order_of(entry: LobbyEntryView) -> tuple[int, int, datetime | None, str]:
    """Sort key: the tables that wait for the account by case, then the dealt tables with someone present, then the
    undealt, then the resting ones by their end, each group by id.
    """
    if entry.waits_on is not None:
        return 0, _WAITING_RANK[entry.waits_on], None, entry.id
    if entry.ends_at is None:
        return (1 if entry.dealt else 2), 0, None, entry.id
    return 3, 0, entry.ends_at, entry.id
