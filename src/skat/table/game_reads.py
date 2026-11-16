from typing import TYPE_CHECKING

from skat.table.game_list import series_list_view_of
from skat.table.game_sheet import game_sheet_of
from skat.table.records import EndedTable, TableId, TableRecord
from skat.table.rules import played_series_of

if TYPE_CHECKING:
    from skat.table.game_list import RamschSeriesEntryView, SeriesEntryView
    from skat.table.game_sheet import GameSheetView
    from skat.table.transactions import TableTransactions


class GameListReads:
    """The reads of the list of finished games and of one game of it, the same for every viewer; the table service is
    built on them.

    A subclass sets the transactions these reads use.
    """

    _transactions: TableTransactions

    def _table_read(self, table_id: str) -> TableRecord | EndedTable | None:
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            return transaction.table(identifier)

    def series_list(self, table_id: str) -> tuple[SeriesEntryView | RamschSeriesEntryView, ...] | None:
        """The list of finished games of the table's current series, or of an ended table's last series that has games;
        None for no table, empty for an ended table that finished no game.
        """
        table = self._table_read(table_id)
        if table is None:
            return None
        played = played_series_of(table)
        return () if played is None else series_list_view_of(played)

    def game_sheet(self, table_id: str, number: int) -> GameSheetView | None:
        """The `number`th game of the series the list shows with the cards it stored, read in one transaction; None for
        no table, a table that finished no game and a number no game has.
        """
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            table = transaction.table(identifier)
            played = None if table is None else played_series_of(table)
            if played is None or not 1 <= number <= len(played.game_list):
                return None
            return game_sheet_of(played, number, transaction.game_cards(identifier, played.number, number))
