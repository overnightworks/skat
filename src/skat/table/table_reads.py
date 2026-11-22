"""The reads of one table for one viewer: its view, the account's member view and acts, who is at the table, the
moments of an account's seats and the agent in a chair.
"""

from typing import TYPE_CHECKING

from skat.table.game_reads import GameListReads
from skat.table.member_place import agent_in_chair, at_the_table
from skat.table.member_view import MemberActs, MemberView, member_acts_of, member_view_of, moment_at
from skat.table.moment import TableMoment
from skat.table.records import Actor, EndedTable, TableId, TableRecord
from skat.table.rules import present_at
from skat.table.views import TableView, view_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime


class TableReads(GameListReads):
    """The reads of one table for one viewer; the table service is built on them.

    A subclass sets the live-lease read and the clock these reads use, besides the transactions.
    """

    _live_leases: Callable[[], frozenset[str]]
    _now: Callable[[], datetime]

    def view(self, actor: Actor, table_id: str, connected_accounts: frozenset[str]) -> TableView | None:
        table = self._table_read(table_id)
        if table is None:
            return None
        present = (
            connected_accounts
            if isinstance(table, EndedTable)
            else present_at(table, connected_accounts, self._live_leases())
        )
        return view_of(table, actor.account_id, present, self._now())

    def accounts_at_the_table(self, table_id: TableId, connected_accounts: frozenset[str]) -> frozenset[str]:
        """Who is at the live table for a call; an ended or missing table counts the open streams only."""
        table = self._table_read(table_id.value)
        return at_the_table(table, connected_accounts) if isinstance(table, TableRecord) else connected_accounts

    def member_view(self, account_id: str, table_id: str, connected_accounts: frozenset[str]) -> MemberView | None:
        """The live table's view for the account that holds a chair there, with whether the table waits for it; None
        for any other account, an ended table and a table that is not there.
        """
        table = self._table_read(table_id)
        if not isinstance(table, TableRecord):
            return None
        present = present_at(table, connected_accounts, self._live_leases())
        return member_view_of(table, account_id, present, self._now())

    def member_acts(self, account_id: str, table_id: str) -> MemberActs | None:
        """The acts of the live table's latest hand for the account that holds a chair there; None for any other
        account, an ended table and a table that is not there.
        """
        table = self._table_read(table_id)
        return member_acts_of(table, account_id) if isinstance(table, TableRecord) else None

    def moments_of(self, account_id: str) -> frozenset[TableMoment]:
        """The moments of the account's seats at the live tables it holds a chair at, from one read; the lobby moment
        when it holds none.
        """
        with self._transactions.begin() as transaction:
            tables = [transaction.table(held.table_id) for held in transaction.tables_of(account_id)]
        moments = frozenset(moment_at(table, account_id) for table in tables if isinstance(table, TableRecord))
        return moments or frozenset({TableMoment.LOBBY})

    def agent_in_chair(self, table_id: str, seat: int) -> str | None:
        """The account of the agent that holds the chair `seat` of the live table; None for a person, a free chair,
        a table that ended and a table that is not there.
        """
        table = self._table_read(table_id)
        return agent_in_chair(table, seat) if isinstance(table, TableRecord) else None
