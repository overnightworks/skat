from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select, update
from webauth.ports import AccountKind

from skat.store.schema import accounts

if TYPE_CHECKING:
    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

__all__ = ["AccountRecord", "PostgresAccounts"]


@dataclass(frozen=True)
class AccountRecord:
    id: str
    username: str
    role: str
    kind: AccountKind


def account_of(row: Row[Any]) -> AccountRecord:
    return AccountRecord(row.id, row.username, row.role, AccountKind(row.kind))


class PostgresAccounts:
    """The accounts of one sign-in entry, in the entry's transaction; the account's id is the issuer's subject.

    `get` compares the id exactly, because Postgres compares text under a deterministic collation by its bytes.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, user_id: str) -> AccountRecord | None:
        row = self._connection.execute(select(accounts).where(accounts.c.id == user_id)).one_or_none()
        return None if row is None else account_of(row)

    def create_for_subject(self, subject: str, username: str, role: str, kind: AccountKind) -> AccountRecord:
        """The username is for display; the trusted issuer decides who a subject is, so no username is taken."""
        row = self._connection.execute(
            insert(accounts).values(id=subject, username=username, role=role, kind=kind.value).returning(accounts)
        ).one()
        return account_of(row)

    def set_role(self, user_id: str, role: str) -> AccountRecord:
        return self._changed(user_id, role=role)

    def set_kind(self, user_id: str, kind: AccountKind) -> AccountRecord:
        return self._changed(user_id, kind=kind.value)

    def _changed(self, user_id: str, **values: str) -> AccountRecord:
        """The changed account; an account that is not there raises, as admission only changes one it just read."""
        row = self._connection.execute(
            update(accounts).where(accounts.c.id == user_id).values(**values).returning(accounts)
        ).one()
        return account_of(row)
