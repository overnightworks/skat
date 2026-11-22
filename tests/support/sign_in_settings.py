import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from skat.web.settings import RealmSettings, ServerSettings

if TYPE_CHECKING:
    from pathlib import Path

TEST_ISSUER = "https://issuer.test.invalid/realms/test"
TEST_PUBLIC_ORIGIN = "https://skat.test.invalid"
# Names no server: settings tests never connect, and a test that does overrides `database_url`.
TEST_DATABASE_URL = "postgresql://skat@database.test.invalid/skat"
# Names no server either: a test that reaches Redis overrides `redis_url`.
TEST_REDIS_URL = "redis://redis.test.invalid:6379/0"
# The realm's names as the platform hands them, by their environment keys; the values are this suite's own.
REALM_ENVIRONMENT = {
    "REALM_CLIENT_ID": "test-client",
    "REALM_LOGIN_GROUP": "/apps/test",
    "REALM_MCP_GROUP": "/apps/test/mcp",
    "REALM_MCP_SCOPE": "mcp-test",
    "REALM_AGENT_GROUP": "/agents",
    "REALM_MCP_CLIENT_ID": "test-agents",
}
TEST_REALM = RealmSettings.model_validate(REALM_ENVIRONMENT)
LOGIN_GROUP = str(TEST_REALM.login_group)
MCP_GROUP = str(TEST_REALM.mcp_group)
AGENT_GROUP = str(TEST_REALM.agent_group)
MCP_SCOPE = TEST_REALM.mcp_scope
MCP_CLIENT_ID = TEST_REALM.mcp_client_id
SESSION_SECRET_BYTES = 36
DATABASE_PASSWORD_BYTES = 18
CLIENT_SECRET_BYTES = 24


@dataclass(frozen=True)
class SignInSettings:
    environment: dict[str, str] = field(repr=False)
    settings: ServerSettings
    client_secret: str = field(repr=False)
    session_secret: str = field(repr=False)
    database_password: str = field(repr=False)


def build_sign_in_settings(directory: Path, **overrides: str | int | Path | None) -> SignInSettings:
    """Write throwaway secret files into `directory`; an override of None leaves that setting out."""
    client_secret = secrets.token_urlsafe(CLIENT_SECRET_BYTES)
    session_secret = secrets.token_urlsafe(SESSION_SECRET_BYTES)
    client_secret_file = directory / "client-secret"
    database_password_file = directory / "database-password"
    session_secret_file = directory / "session-secret"
    client_secret_file.write_text(client_secret + "\n")
    session_secret_file.write_text(session_secret + "\n")
    database_password = secrets.token_urlsafe(DATABASE_PASSWORD_BYTES)
    database_password_file.write_text(database_password + "\n")
    values: dict[str, str | int | Path | None] = {
        "oidc_issuer": TEST_ISSUER,
        "oidc_client_secret_file": client_secret_file,
        "database_url": TEST_DATABASE_URL,
        "database_password_file": database_password_file,
        "redis_url": TEST_REDIS_URL,
        "public_origin": TEST_PUBLIC_ORIGIN,
        "session_secret_file": session_secret_file,
        **overrides,
    }
    present = {name: value for name, value in values.items() if value is not None}
    return SignInSettings(
        environment={**REALM_ENVIRONMENT, **{f"SKAT_{name.upper()}": str(value) for name, value in present.items()}},
        settings=ServerSettings(realm=TEST_REALM, **present),
        client_secret=client_secret,
        session_secret=session_secret,
        database_password=database_password,
    )
