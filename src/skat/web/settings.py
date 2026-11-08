from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

from pydantic import AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from skat.web.constants import DEFAULT_HOST, DEFAULT_PORT, OIDC_CLIENT_ID


def _require_no_trailing_slash(issuer: str) -> str:
    if issuer.endswith("/"):
        raise ValueError("must not end with a slash")
    return issuer


def _require_origin_without_path(origin: str) -> str:
    if origin.removeprefix("https://").removeprefix("http://").partition("/")[1]:
        raise ValueError("must be an origin without a path")
    return origin


def _require_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("must be an absolute path")
    return path


def _require_postgres_url_without_password(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        # The parser's message quotes the authority, which may hold the password.
        raise ValueError("must be a postgresql URL") from None
    if parts.scheme != "postgresql":
        raise ValueError("must be a postgresql URL")
    if not (parts.hostname and parts.username and parts.path.removeprefix("/")):
        raise ValueError("must name a host, a user and a database")
    if parts.password is not None or "password" in parse_qs(parts.query):
        raise ValueError("must not carry a password")
    return url


IssuerUrl = Annotated[str, AfterValidator(_require_no_trailing_slash)]
OriginUrl = Annotated[str, AfterValidator(_require_origin_without_path)]
AbsolutePath = Annotated[Path, AfterValidator(_require_absolute_path)]
PasswordlessPostgresUrl = Annotated[str, AfterValidator(_require_postgres_url_without_password)]


class DatabaseSettings(BaseSettings):
    """The settings `skat migrate` needs, so it runs before any other setting or the page build is read."""

    # The settings are secrets or name them, so a refusal never echoes an input.
    model_config = SettingsConfigDict(env_prefix="SKAT_", hide_input_in_errors=True)

    database_url: PasswordlessPostgresUrl = Field(repr=False)
    database_password_file: AbsolutePath = Field(repr=False)


class ServerSettings(DatabaseSettings):
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    oidc_issuer: IssuerUrl
    oidc_client_id: str = OIDC_CLIENT_ID
    oidc_client_secret_file: AbsolutePath = Field(repr=False)
    public_origin: OriginUrl
    session_secret_file: AbsolutePath = Field(repr=False)
    # Addresses and CIDR blocks, comma-separated, of the proxies allowed to name the client in X-Forwarded-For.
    trusted_proxies: str = ""
