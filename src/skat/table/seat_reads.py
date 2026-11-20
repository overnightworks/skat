from skat.table.game_reads import GameListReads
from skat.table.member_place import SeatedAccounts, agent_in_chair, at_the_table, seated_accounts_of
from skat.table.records import TableId, TableRecord

__all__ = ["SeatReads"]


class SeatReads(GameListReads):
    """The reads of who holds the chairs of one live table; the table service is built on them."""

    def accounts_at_the_table(self, table_id: TableId, connected_accounts: frozenset[str]) -> frozenset[str]:
        """Who is at the live table for a call; an ended or missing table counts the open streams only."""
        table = self._table_read(table_id.value)
        return at_the_table(table, connected_accounts) if isinstance(table, TableRecord) else connected_accounts

    def seated_accounts(self, table_id: str) -> SeatedAccounts | None:
        """Who holds each occupied chair of the live table, from one read; None for an ended table and a table that is
        not there.
        """
        table = self._table_read(table_id)
        return seated_accounts_of(table) if isinstance(table, TableRecord) else None

    def agent_in_chair(self, table_id: str, seat: int) -> str | None:
        """The account of the agent that holds the chair `seat` of the live table; None for a person, a free chair,
        a table that ended and a table that is not there.
        """
        table = self._table_read(table_id)
        return agent_in_chair(table, seat) if isinstance(table, TableRecord) else None
