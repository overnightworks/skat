"""A next-deal pause is a row beside its table: the deadline after which any pod deals the table's next hand, on the
database's clock, so it outlives the pod that wrote it.
"""

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert as upsert

from skat.store.schema import next_deals, tables

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


def store_next_deal(connection: Connection, table_id: str, seconds: float, *, replace: bool) -> None:
    """Store the table's pause as due `seconds` from now: in place of a pending one when `replace`, else only where it
    has none. Only a live table that was dealt on gets one.
    """
    dealt = select(tables.c.id, func.now() + func.make_interval(0, 0, 0, 0, 0, 0, literal(seconds))).where(
        tables.c.id == table_id, tables.c.end_reason.is_(None), tables.c.dealer.is_not(None)
    )
    written = upsert(next_deals).from_select(["table_id", "due_at"], dealt)
    connection.execute(
        written.on_conflict_do_update(index_elements=[next_deals.c.table_id], set_={"due_at": written.excluded.due_at})
        if replace
        else written.on_conflict_do_nothing(index_elements=[next_deals.c.table_id])
    )


def locked_next_deal_due(connection: Connection, table_id: str) -> bool:
    """Whether the table's pause is over on the database's clock, its row locked by the transaction; False without
    one.
    """
    due = connection.execute(
        select(next_deals.c.due_at <= func.now()).where(next_deals.c.table_id == table_id).with_for_update()
    ).scalar_one_or_none()
    return bool(due)


def delete_next_deal(connection: Connection, table_id: str) -> None:
    connection.execute(delete(next_deals).where(next_deals.c.table_id == table_id))


def due_next_deals(connection: Connection, limit: int) -> tuple[str, ...]:
    """The ids of at most `limit` tables whose pause is over on the database's clock, the earliest first; no row is
    locked, so the list is a candidate list.
    """
    return tuple(
        connection.execute(
            select(next_deals.c.table_id)
            .where(next_deals.c.due_at <= func.now())
            .order_by(next_deals.c.due_at)
            .limit(limit)
        ).scalars()
    )
