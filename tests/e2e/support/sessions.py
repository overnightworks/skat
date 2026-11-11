from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.e2e.support.server import RunningServer


def end_sessions_of(server: RunningServer, username: str) -> None:
    """Ends every session of the person who signed in as `username`, keeping the account as a sign-out would."""
    sessions = server.stores.sessions
    records = sessions.records_of(f"subject-{username}")
    assert records.account is not None
    assert records.sessions, f"{username} has no session to end"
    account = records.account
    sessions.delete_for_user(account.id)
    server.stores.accounts.create_for_subject(account.id, account.username, role=account.role, kind=account.kind)
