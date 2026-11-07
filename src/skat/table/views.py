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


def view_of(table: TableRecord, viewer_account_id: str) -> TableView:
    """The table as one account sees it: only the viewer's own chair is marked mine."""
    return TableView(
        id=table.id.value,
        version=table.version,
        chairs=tuple(
            ChairView(
                seat=chair.seat,
                occupant_name=None if chair.occupant is None else chair.occupant.display_name,
                is_mine=chair.occupant is not None and chair.occupant.account_id == viewer_account_id,
            )
            for chair in table.chairs
        ),
    )
