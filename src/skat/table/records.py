import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Self

from skat.engine.bidding import BidRefusal
from skat.engine.declaration import DeclarationRefusal
from skat.engine.tricks import PlayRefusal

if TYPE_CHECKING:
    from skat.engine.bidding import AuctionStep
    from skat.engine.deal import Deal
    from skat.engine.declaration import DeclaringStep
    from skat.engine.tricks import CardPlayed
    from skat.table.game_list import ListEntry

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
class SitDown:
    """The command to take a chair; `command_id` is the client's key for retrying it."""

    command_id: str
    table_id: str
    seat: int


@dataclass(frozen=True)
class StandUp:
    """The command to leave one's own chair."""

    command_id: str
    table_id: str


class Refusal(StrEnum):
    """Why a table command changed nothing."""

    SEAT_TAKEN = "seat-taken"
    ALREADY_SEATED = "already-seated"
    NOT_SEATED = "not-seated"
    HAND_RUNNING = "hand-running"
    NO_HAND = "no-hand"
    STALE_VERSION = "stale-version"
    WRONG_PHASE = "wrong-phase"
    NOT_DECLARER = "not-declarer"


type CommandRefusal = Refusal | BidRefusal | DeclarationRefusal | PlayRefusal

# `PlayRefusal` shares its `over` and `not-your-turn` tokens with `BidRefusal`: the wire string is the same either way.
_REFUSALS_BY_TOKEN: Final[dict[str, CommandRefusal]] = {
    refusal.value: refusal for refusal in (*Refusal, *PlayRefusal, *BidRefusal, *DeclarationRefusal)
}


def parsed_refusal(token: str) -> CommandRefusal:
    """The refusal a stored receipt names, whichever owner holds the token; a token nobody owns raises."""
    return _REFUSALS_BY_TOKEN[token]


@dataclass(frozen=True)
class Occupant:
    account_id: str
    display_name: str


@dataclass(frozen=True)
class Chair:
    seat: int
    occupant: Occupant | None


@dataclass(frozen=True)
class HandProgress:
    """What has happened in the running hand so far; a later phase adds its own field."""

    auction: tuple[AuctionStep, ...] = ()
    declaring: tuple[DeclaringStep, ...] = ()
    plays: tuple[CardPlayed, ...] = ()


@dataclass(frozen=True)
class TableRecord:
    """A table as stored; its game list outlives every deal and goes only with the table."""

    id: TableId
    version: int
    chairs: tuple[Chair, ...]
    dealer: int | None = None
    hand: Deal | None = None
    progress: HandProgress = HandProgress()
    game_list: tuple[ListEntry, ...] = ()


@dataclass(frozen=True)
class NewHand:
    """A hand about to start: the seat that deals it and the cards dealt."""

    dealer: int
    hand: Deal


@dataclass(frozen=True)
class Decision:
    """The table after a command; a refusal leaves it as it was and names who holds a taken chair."""

    table: TableRecord
    refusal: CommandRefusal | None = None
    holder: str | None = None


@dataclass(frozen=True)
class Receipt:
    """What a command did, kept under (account, command id) so a retry answers with the same result."""

    account_id: str
    command_id: str
    command: str
    payload: str
    table_id: TableId
    refusal: CommandRefusal | None = None
    holder: str | None = None


@dataclass(frozen=True)
class Replay:
    """A stored receipt's request, with the table it produced."""

    command: str
    payload: str
    table: TableRecord
    refusal: CommandRefusal | None = None
    holder: str | None = None
