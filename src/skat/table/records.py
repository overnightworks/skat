import re
import secrets
from dataclasses import dataclass
from typing import Final, Self

TABLE_ID_BYTES: Final = 16
_TABLE_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class TableId:
    """An opaque 128-bit id, written as 32 lower-case hex digits."""

    value: str

    @classmethod
    def random(cls) -> Self:
        return cls(secrets.token_bytes(TABLE_ID_BYTES).hex())

    @classmethod
    def parse(cls, text: str) -> Self | None:
        return cls(text) if _TABLE_ID.fullmatch(text) else None


@dataclass(frozen=True)
class Actor:
    """The account behind a request, as the server resolved it; a client never names one."""

    account_id: str
    display_name: str


@dataclass(frozen=True)
class CreateTable:
    """The command to open a table; `command_id` is the client's key for retrying it."""

    command_id: str


@dataclass(frozen=True)
class Occupant:
    account_id: str
    display_name: str


@dataclass(frozen=True)
class Chair:
    seat: int
    occupant: Occupant | None


@dataclass(frozen=True)
class TableRecord:
    id: TableId
    version: int
    chairs: tuple[Chair, ...]


@dataclass(frozen=True)
class Receipt:
    """What a command did, kept under (account, command id) so a retry answers with the same result."""

    account_id: str
    command_id: str
    command: str
    payload: str
    table_id: TableId


@dataclass(frozen=True)
class Replay:
    """A stored receipt's request, with the table it produced."""

    command: str
    payload: str
    table: TableRecord
