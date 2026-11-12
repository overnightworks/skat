"""The lobby's list of the tables an account holds a chair at, projected from each table's member view.

Every entry is built for one account from its own chairs, so no table reaches an account that holds none there. The
entries are ordered by what the account has to do: the tables that wait for it first.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skat.table.awaiting import WaitingCase, waiting_case
from skat.table.member_view import member_view_of
from skat.table.records import OccupantKind, TableRecord
from skat.table.rules import hand_was_dealt, present_at
from skat.table.views import turn_seat_of

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from skat.table.member_view import MemberView
    from skat.table.records import TableId
    from skat.table.transactions import PausedFacts, TableTransactions

__all__ = ["LobbyChairView", "LobbyEntryView", "my_tables"]

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


@dataclass(frozen=True)
class LobbyEntryView:
    """A live table the account holds a chair at, with whether and why it waits for the account.

    `title_name` is the name its opener had when he opened it, None before the name was kept; `game_number` and
    `game_count` are None for a table without a series. `ends_at` is the instant the table ends, in UTC, and is set
    only when a hand was dealt and nobody is present. The entry names no card, no card count and no account.
    """

    id: str
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


def my_tables(
    transactions: TableTransactions,
    live_leases: frozenset[str],
    account_id: str,
    held_ids: Iterable[TableId],
    connected_by_table: Mapping[str, frozenset[str]],
    days: int,
) -> tuple[LobbyEntryView, ...]:
    """The entries of the tables the account holds a chair at, in the lobby's order.

    `held_ids` is a candidate list from an unlocked read, so each table is read again in one transaction under its
    shared row lock: an ended table and a table whose chair the account left meanwhile are skipped. A table with
    nobody in `connected_by_table` has nobody connected; `live_leases` are the agents whose lease runs.
    """
    entries: list[LobbyEntryView] = []
    with transactions.begin() as transaction:
        for table_id in held_ids:
            table = transaction.table(table_id)
            if not isinstance(table, TableRecord):
                continue
            present = present_at(table, connected_by_table.get(table_id.value, frozenset()), live_leases)
            member = member_view_of(table, account_id, present)
            if member is not None:
                entries.append(_entry_of(table, member, present, transaction.paused_facts(table_id), days))
    return tuple(sorted(entries, key=_order_of))


def _entry_of(
    table: TableRecord, member: MemberView, present: frozenset[str], facts: PausedFacts, days: int
) -> LobbyEntryView:
    view = member.view
    turn_seat = turn_seat_of(view.hand)
    return LobbyEntryView(
        id=view.id,
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
            )
            for chair in view.chairs
        ),
    )


def _end_of(table: TableRecord, present: frozenset[str], facts: PausedFacts, days: int) -> datetime | None:
    if not hand_was_dealt(table) or present:
        return None
    assert facts.last_played_at is not None  # noqa: S101 - narrows the type; a dealt table has its time
    return facts.last_played_at.astimezone(UTC) + timedelta(days=days)


def _order_of(entry: LobbyEntryView) -> tuple[int, int, datetime | None, str]:
    """Sort key: the tables that wait for the account by case, then the dealt tables with someone present, then the
    undealt, then the resting ones by their end, each group by id.
    """
    if entry.waits_on is not None:
        return 0, _WAITING_RANK[entry.waits_on], None, entry.id
    if entry.ends_at is None:
        return (1 if entry.dealt else 2), 0, None, entry.id
    return 3, 0, entry.ends_at, entry.id
