from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skat.table.records import TableRecord


@dataclass(frozen=True)
class ChairView:
    seat: int
    occupant_name: str | None
    is_mine: bool


@dataclass(frozen=True)
class TableView:
    id: str
    version: int
    chairs: tuple[ChairView, ...]
    watchers: int


def view_of(table: TableRecord, viewer_account_id: str, connected_accounts: frozenset[str]) -> TableView:
    """The table as one account sees it: only the viewer's own chair is marked mine.

    The watchers are the connected accounts without a chair, each counted once.
    """
    seated = {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}
    return TableView(
        id=table.id.value,
        version=table.version,
        watchers=len(connected_accounts - seated),
        chairs=tuple(
            ChairView(
                seat=chair.seat,
                occupant_name=None if chair.occupant is None else chair.occupant.display_name,
                is_mine=chair.occupant is not None and chair.occupant.account_id == viewer_account_id,
            )
            for chair in table.chairs
        ),
    )
