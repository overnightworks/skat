import re
from pathlib import Path
from typing import Annotated, Any, Final
from urllib.parse import urlsplit

from pydantic import AfterValidator, BeforeValidator, Field
from pydantic_settings import BaseSettings, EnvSettingsSource, NoDecode, PydanticBaseSettingsSource, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from webauth.admission import GroupPath

from skat.web.constants import DEFAULT_HOST, DEFAULT_PORT

DEFAULT_EMPTY_TABLE_SECONDS: Final = 1800
DEFAULT_PAUSED_TABLE_DAYS: Final = 90
DEFAULT_ENDED_TABLE_DAYS: Final = 7
DEFAULT_STREAMS_PER_ACCOUNT: Final = 12
HIGHEST_TABLE_DAYS: Final = 36_500


def _require_no_trailing_slash(issuer: str) -> str:
    if issuer.endswith("/"):
        raise ValueError("must not end with a slash")
    return issuer


# The browser's own serialisation of an https origin. The framed table compares `event.origin` with `call_origin`, and
# the call page compares it with Skat's origin, each byte for byte.
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


def _require_visible_text(text: str) -> str:
    if not text.isprintable() or not text.strip():
        raise ValueError("must be text with a visible character and no control character")
    return text


def _require_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("must be an absolute path")
    return path


def _require_postgres_url_without_password(url: str) -> str:
    try:
        parsed = make_url(url, keep_blank_values=True)  # NOSONAR(S930) SQLAlchemy 2.1 declares keep_blank_values
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


_REDIS_DATABASE_PATH = re.compile(r"(/\d+)?", re.ASCII)


def _require_redis_url_without_credentials(url: str) -> str:
    try:
        parsed = urlsplit(url)
        # Reading the port validates it.
        _ = parsed.port
    except ValueError:
        # The parser's messages quote parts of the URL.
        raise ValueError("must be a redis URL") from None
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise ValueError("must be a redis or rediss URL naming a host")
    if "@" in parsed.netloc:
        raise ValueError("must not carry credentials")
    # redis-py reads query parameters over its own options, such as the timeouts the client is built with.
    if parsed.query or parsed.fragment or not _REDIS_DATABASE_PATH.fullmatch(parsed.path):
        raise ValueError("must end in at most a database number")
    return url


IssuerUrl = Annotated[str, AfterValidator(_require_no_trailing_slash)]
OriginUrl = Annotated[str, AfterValidator(_require_browser_origin)]
OptionalOriginUrl = Annotated[OriginUrl | None, BeforeValidator(_unset_when_empty)]
VisibleText = Annotated[str, AfterValidator(_require_visible_text)]
OptionalAccountId = Annotated[VisibleText | None, BeforeValidator(_unset_when_empty)]
AbsolutePath = Annotated[Path, AfterValidator(_require_absolute_path)]
PasswordlessPostgresUrl = Annotated[str, AfterValidator(_require_postgres_url_without_password)]
CredentiallessRedisUrl = Annotated[str, AfterValidator(_require_redis_url_without_credentials)]
# NoDecode: pydantic-settings JSON-decodes the value of a dataclass-typed field before any validator runs.
RealmGroup = Annotated[GroupPath, NoDecode, BeforeValidator(GroupPath)]


class RealmSettings(BaseSettings):
    """The realm's names for Skat, as the platform hands them; each field is read from its own environment key."""

    model_config = SettingsConfigDict(hide_input_in_errors=True, populate_by_name=True)

    client_id: str = Field(validation_alias="REALM_CLIENT_ID", min_length=1)
    login_group: RealmGroup = Field(validation_alias="REALM_LOGIN_GROUP")
    # The scope and audience a token for the MCP path carries.
    mcp_scope: str = Field(validation_alias="REALM_MCP_SCOPE", min_length=1)
    # The group whose members the MCP gate admits.
    mcp_group: RealmGroup = Field(validation_alias="REALM_MCP_GROUP")
    # The group of agents' own accounts, admitted from any client.
    agent_group: RealmGroup = Field(validation_alias="REALM_AGENT_GROUP")
    # The client agents sign in with.
    mcp_client_id: str = Field(validation_alias="REALM_MCP_CLIENT_ID", min_length=1)


def _realm_from_environment() -> RealmSettings:
    # The required values come from the environment, which the type checker cannot see.
    return RealmSettings()  # pyright: ignore[reportCallIssue]


class DatabaseSettings(BaseSettings):
    """The settings `skat migrate` needs, so it runs before any other setting or the page build is read."""

    # The settings are secrets or name them, so a refusal never echoes an input.
    model_config = SettingsConfigDict(env_prefix="SKAT_", hide_input_in_errors=True)

    database_url: PasswordlessPostgresUrl = Field(repr=False)
    database_password_file: AbsolutePath = Field(repr=False)
    # The account `skat migrate` installs the operator's rule set on; unset, no set is installed.
    operator_account_id: OptionalAccountId = None


class _EnvironmentWithoutRealm(EnvSettingsSource):
    """The environment as a source for every field but `realm`, which only the REALM_* variables fill."""

    def __call__(self) -> dict[str, Any]:
        return {name: value for name, value in super().__call__().items() if name != "realm"}


class ServerSettings(DatabaseSettings):
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003, V107 the hook's fixed signature
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, _EnvironmentWithoutRealm(settings_cls), dotenv_settings, file_secret_settings)

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    oidc_issuer: IssuerUrl
    # Read from the REALM_* variables alone; the environment source never fills this field.
    realm: RealmSettings = Field(default_factory=_realm_from_environment)
    oidc_client_secret_file: AbsolutePath = Field(repr=False)
    public_origin: OriginUrl
    session_secret_file: AbsolutePath = Field(repr=False)
    # The one origin whose pages may frame Skat; unset or empty allows no framing.
    call_origin: OptionalOriginUrl = None
    # Addresses and CIDR blocks, comma-separated, of the proxies allowed to name the client in X-Forwarded-For.
    trusted_proxies: str = ""
    # How long a seated member whose last stream ended keeps the chair while no hand runs.
    chair_hold_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    # How long a table on which no hand was dealt stays after nobody is connected to it, before it ends; whole seconds,
    # which the ended table's answer names.
    empty_table_seconds: int = Field(default=DEFAULT_EMPTY_TABLE_SECONDS, gt=0)
    # How many days after its last deal or step of play a table on which a hand was dealt ends; whole days, at most a
    # hundred years so the end is always a date.
    paused_table_days: int = Field(default=DEFAULT_PAUSED_TABLE_DAYS, gt=0, le=HIGHEST_TABLE_DAYS)
    # How many days after its end an ended table's link names why it ended; then a table with no game in the history is
    # deleted and the closer's name of the others is cleared. Whole days, at most a hundred years.
    ended_table_days: int = Field(default=DEFAULT_ENDED_TABLE_DAYS, gt=0, le=HIGHEST_TABLE_DAYS)
    # How many lobby and table streams one account may hold open at once; one more is refused with a 429.
    streams_per_account: int = Field(default=DEFAULT_STREAMS_PER_ACCOUNT, gt=0)
    # The Redis every pod shares for its sign-in limits and its wakes; it keeps nothing durable. Like the database URL,
    # it carries no credentials.
    redis_url: CredentiallessRedisUrl = Field(repr=False)
