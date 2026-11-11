from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from skat.store.schema import member_book
from skat.table.member_place import BookEntry, OpenInvitation
from skat.table.records import TableId

if TYPE_CHECKING:
    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

__all__ = ["accounts_at", "forget_table", "locked_entries_of", "locked_entry", "save_entry"]


def _entry_of(row: Row[tuple[str, str, int, str | None, object, str | None, str | None]]) -> BookEntry:
    invitation = (
        None
        if row.invitation_id is None
        else OpenInvitation(row.invitation_id, row.invitation_expires_at, row.owner_account, row.inviter_account)
    )
    return BookEntry(TableId(row.table_id), row.agent_account, row.epoch, invitation)


def locked_entry(connection: Connection, table_id: str, agent_account: str) -> BookEntry | None:
    row = connection.execute(
        select(member_book)
        .where(member_book.c.table_id == table_id, member_book.c.agent_account == agent_account)
        .with_for_update()
    ).one_or_none()
    return None if row is None else _entry_of(row)


def locked_entries_of(connection: Connection, agent_account: str) -> tuple[BookEntry, ...]:
    rows = connection.execute(
        select(member_book)
        .where(member_book.c.agent_account == agent_account)
        .order_by(member_book.c.table_id)
        .with_for_update()
    )
    return tuple(_entry_of(row) for row in rows)


def save_entry(connection: Connection, entry: BookEntry) -> None:
    invitation = entry.invitation
    values = {
        "epoch": entry.epoch,
        "invitation_id": None if invitation is None else invitation.id,
        "invitation_expires_at": None if invitation is None else invitation.expires_at,
        "owner_account": None if invitation is None else invitation.owner_account,
        "inviter_account": None if invitation is None else invitation.inviter_account,
    }
    insertion = insert(member_book).values(table_id=entry.table_id.value, agent_account=entry.agent_account, **values)
    connection.execute(
        insertion.on_conflict_do_update(
            index_elements=[member_book.c.table_id, member_book.c.agent_account], set_=values
        )
    )


def accounts_at(connection: Connection, table_id: str) -> frozenset[str]:
    return frozenset(
        connection.execute(select(member_book.c.agent_account).where(member_book.c.table_id == table_id)).scalars()
    )


def forget_table(connection: Connection, table_id: str) -> None:
    connection.execute(delete(member_book).where(member_book.c.table_id == table_id))
