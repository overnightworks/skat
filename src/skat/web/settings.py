import re
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from skat.web.constants import DEFAULT_HOST, DEFAULT_PORT, OIDC_CLIENT_ID


def _require_no_trailing_slash(issuer: str) -> str:
    if issuer.endswith("/"):
        raise ValueError("must not end with a slash")
    return issuer


# The browser's own serialisation of an https origin: the call page compares `event.origin` with it byte for byte.
_BROWSER_ORIGIN = re.compile(r"https://(?P<host>[a-z0-9.-]+)(:(?P<port>[1-9]\d{0,4}))?", re.ASCII)
_HOST_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", re.ASCII)
_CANONICAL_IPV4_OCTET = re.compile(r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)", re.ASCII)
_NUMBER_LABEL = re.compile(r"\d+|0x[0-9a-f]*", re.ASCII)
_HIGHEST_PORT = 65535
_HTTPS_PORT = 443
_IPV4_OCTET_COUNT = 4


def _is_canonical_ipv4(labels: list[str]) -> bool:
    return len(labels) == _IPV4_OCTET_COUNT and all(_CANONICAL_IPV4_OCTET.fullmatch(label) for label in labels)


def _require_browser_origin(origin: str) -> str:
    matched = _BROWSER_ORIGIN.fullmatch(origin)
    message = "must be an https origin as the browser writes it: lowercase host, no path, no port 443"
    if not matched:
        raise ValueError(message)
    port = int(matched["port"]) if matched["port"] else None
    if port is not None and (port > _HIGHEST_PORT or port == _HTTPS_PORT):
        raise ValueError(message)
    labels = matched["host"].split(".")
    if not all(_HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError(message)
    # A host ending in a number is an IPv4 address to the browser, which writes it as four canonical numbers.
    if _NUMBER_LABEL.fullmatch(labels[-1]) and not _is_canonical_ipv4(labels):
        raise ValueError(message)
    return origin


def _unset_when_empty(origin: object) -> object:
    return None if origin == "" else origin


def _require_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("must be an absolute path")
    return path


def _require_postgres_url_without_password(url: str) -> str:
    try:
        parsed = make_url(url, keep_blank_values=True)
    except ArgumentError, ValueError:
        # The parser's messages quote parts of the URL, which may hold the password.
        raise ValueError("must be a postgresql URL") from None
    if parsed.drivername != "postgresql":
        raise ValueError("must be a postgresql URL")
    if not (parsed.host and parsed.username and parsed.database):
        raise ValueError("must name a host, a user and a database")
    if parsed.password is not None:
        raise ValueError("must not carry a password")
    # libpq reads query parameters over the authority, so any of them can redirect the password.
    if parsed.query:
        raise ValueError("must not carry query parameters")
    return url


IssuerUrl = Annotated[str, AfterValidator(_require_no_trailing_slash)]
OriginUrl = Annotated[str, AfterValidator(_require_browser_origin)]
OptionalOriginUrl = Annotated[OriginUrl | None, BeforeValidator(_unset_when_empty)]
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
    # The one origin whose pages may frame Skat; unset or empty allows no framing.
    call_origin: OptionalOriginUrl = None
    # Addresses and CIDR blocks, comma-separated, of the proxies allowed to name the client in X-Forwarded-For.
    trusted_proxies: str = ""
    # How long a seated member whose last stream ended keeps the chair while no hand runs.
    chair_hold_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
