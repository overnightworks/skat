from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.e2e.support.server import RunningServer


def end_sessions_of(server: RunningServer, username: str) -> None:
    """Ends every session of the person who signed in as `username`, as a sign-out elsewhere would."""
    sessions = server.stores.sessions
    ended = [id_ for id_, row in sessions.snapshot().rows.items() if row.user_id == f"subject-{username}"]
    assert ended, f"{username} has no session to end"
    for session_id in ended:
        sessions.delete(session_id)
