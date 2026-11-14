from typing import TYPE_CHECKING

from sqlalchemy import func, select

from skat.store.schema import sessions

if TYPE_CHECKING:
    from tests.e2e.support.server import RunningServer


def holds_a_session(server: RunningServer, username: str) -> bool:
    """Whether the database holds a session of the person who signed in as `username`."""
    with server.engine.connect() as connection:
        held = connection.execute(
            select(func.count()).select_from(sessions).where(sessions.c.account_id == f"subject-{username}")
        ).scalar_one()
    return held > 0


def end_sessions_of(server: RunningServer, username: str) -> None:
    """Ends every session of the person who signed in as `username`, keeping the account as a sign-out would."""
    ended = server.stores.sessions.delete_for_user(f"subject-{username}")
    assert ended, f"{username} has no session to end"
