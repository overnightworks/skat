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
TABLE_ID_PATTERN: Final = "[0-9a-f]{32}"
SERIES_LENGTH_STEP: Final = 3
SERIES_LENGTH_MIN: Final = 3
SERIES_LENGTH_MAX: Final = 99
_TABLE_ID = re.compile(TABLE_ID_PATTERN)


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
    """The command to open a table; `command_id` is the client's key for retrying it, `series_length` the number of
    games its series runs, or None for a table that plays on.
    """

    command_id: str
    series_length: int | None = None


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
    NO_RESULT = "no-result"
    STALE_RESULT = "stale-result"
    SERIES_OVER = "series-over"


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
    """A chair and who sits on it; `ready` says its occupant is ready for the next hand,
    by a tap of „Weiter“ or by sitting down while a result is pending."""

    seat: int
    occupant: Occupant | None
    ready: bool = False


@dataclass(frozen=True)
class HandProgress:
    """What has happened in the running hand so far; a later phase adds its own field."""

    auction: tuple[AuctionStep, ...] = ()
    declaring: tuple[DeclaringStep, ...] = ()
    plays: tuple[CardPlayed, ...] = ()


@dataclass(frozen=True)
class Series:
    """A table's series: its fixed `length` in games and the `deals` made so far, a passed-in hand included."""

    length: int
    deals: int

    def __post_init__(self) -> None:
        if not SERIES_LENGTH_MIN <= self.length <= SERIES_LENGTH_MAX or self.length % SERIES_LENGTH_STEP:
            message = (
                f"a series length is a multiple of {SERIES_LENGTH_STEP} from {SERIES_LENGTH_MIN} to {SERIES_LENGTH_MAX}"
            )
            raise ValueError(message)
        if not 0 <= self.deals <= self.length:
            message = f"a series of {self.length} games has no {self.deals} deals"
            raise ValueError(message)


@dataclass(frozen=True)
class TableRecord:
    """A table as stored; its game list outlives every deal and goes only with the table."""

    id: TableId
    version: int
    chairs: tuple[Chair, ...]
    dealer: int | None
    hand: Deal | None
    progress: HandProgress
    game_list: tuple[ListEntry, ...]
    series: Series | None


class EndReason(StrEnum):
    """Why a table ended; the stored token and the one the answer carries."""

    EMPTY = "empty"


@dataclass(frozen=True)
class EndedTable:
    """What stays of an ended table: its id, version and reason, and for an empty one how long nobody was there."""

    id: TableId
    version: int
    reason: EndReason
    empty_seconds: int


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
    table: TableRecord | EndedTable
    refusal: CommandRefusal | None = None
    holder: str | None = None
