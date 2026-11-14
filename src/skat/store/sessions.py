import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr
from sqlalchemy import delete, insert, select, update

from skat.store.accounts import AccountRecord, account_of
from skat.store.schema import accounts, sessions

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from sqlalchemy import Row, Select
    from sqlalchemy.engine import Connection

__all__ = ["PostgresSessionRecords", "StoredSession"]


@dataclass(frozen=True)
class StoredSession:
    id: str = field(repr=False)
    user: AccountRecord
    created_at: datetime
    expires_at: datetime
    refresh_token: SecretStr | None = field(repr=False)
    id_token: SecretStr | None = field(repr=False)
    account_language: str | None


def _hash_of(session_id: str) -> str:
    """The text a session is stored under: its id is a bearer secret, and the table holds only this hash of it."""
    return hashlib.sha256(session_id.encode()).hexdigest()


def _secret(token: str | None) -> SecretStr | None:
    return None if token is None else SecretStr(token)


def _stored(session_id: str, row: Row[Any]) -> StoredSession:
    return StoredSession(
        id=session_id,
        user=account_of(row),
        created_at=row.created_at,
        expires_at=row.expires_at,
        refresh_token=_secret(row.refresh_token),
        id_token=_secret(row.id_token),
        account_language=row.account_language,
    )


def _with_account(session_id: str) -> Select[Any]:
    return (
        select(sessions, accounts)
        .join(accounts, accounts.c.id == sessions.c.account_id)
        .where(sessions.c.id_hash == _hash_of(session_id))
    )


class PostgresSessionRecords:
    """The sessions, each call run in the transaction `connect` opens: one the call commits for the session gate,
    the sign-in entry's own for a call inside an entry.

    A session is stored under the hash of the id webauth mints for it and handed back with the raw id; an id the
    table holds already, an expired session's included, is refused by the primary key. The refresh and ID tokens are
    stored as they are.
    """

    def __init__(self, connect: Callable[[], AbstractContextManager[Connection]]) -> None:
        self._connect = connect

    def create(
        self,
        user_id: str,
        *,
        session_id: str,
        now: datetime,
        expires_at: datetime,
        refresh_token: SecretStr | None,
        id_token: SecretStr | None,
        account_language: str | None,
    ) -> StoredSession:
        with self._connect() as connection:
            connection.execute(
                insert(sessions).values(
                    id_hash=_hash_of(session_id),
                    account_id=user_id,
                    created_at=now,
                    expires_at=expires_at,
                    refresh_token=None if refresh_token is None else refresh_token.get_secret_value(),
                    id_token=None if id_token is None else id_token.get_secret_value(),
                    account_language=account_language,
                )
            )
            return _stored(session_id, connection.execute(_with_account(session_id)).one())

    def load(self, session_id: str) -> StoredSession | None:
        with self._connect() as connection:
            row = connection.execute(_with_account(session_id)).one_or_none()
        return None if row is None else _stored(session_id, row)

    def touch(self, session_id: str, *, expires_at: datetime) -> bool:
        return self._updated(session_id, expires_at=expires_at)

    def replace_refresh_token(self, session_id: str, *, refresh_token: SecretStr) -> bool:
        return self._updated(session_id, refresh_token=refresh_token.get_secret_value())

    def delete(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(delete(sessions).where(sessions.c.id_hash == _hash_of(session_id)))

    def delete_for_user(self, user_id: str) -> int:
        """Ends every session of the account and keeps the account."""
        with self._connect() as connection:
            return connection.execute(delete(sessions).where(sessions.c.account_id == user_id)).rowcount

    def prune_overflow(self, user_id: str, keep_newest: int) -> None:
        overflow = (
            select(sessions.c.id_hash)
            .where(sessions.c.account_id == user_id)
            .order_by(sessions.c.created_at.desc(), sessions.c.id_hash)
            .offset(keep_newest)
        )
        with self._connect() as connection:
            connection.execute(delete(sessions).where(sessions.c.id_hash.in_(overflow)))

    def delete_expired(self, now: datetime) -> int:
        """Deletes the sessions expired at `now` and returns how many went; a repeat deletes none."""
        with self._connect() as connection:
            return connection.execute(delete(sessions).where(sessions.c.expires_at < now)).rowcount

    def _updated(self, session_id: str, **values: object) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                update(sessions).where(sessions.c.id_hash == _hash_of(session_id)).values(**values)
            )
            return result.rowcount == 1
