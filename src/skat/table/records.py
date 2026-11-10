import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Self

from skat.engine.bidding import BidRefusal
from skat.engine.declaration import DeclarationRefusal
from skat.engine.kontra import KontraOptions, KontraRefusal
from skat.engine.tricks import PlayRefusal

if TYPE_CHECKING:
    from skat.engine.bidding import AuctionStep
    from skat.engine.bock import BockOptions, BockRounds
    from skat.engine.deal import Deal, Position
    from skat.engine.declaration import DeclaringStep
    from skat.engine.kontra import WordSaid
    from skat.engine.tricks import CardPlayed
    from skat.table.game_list import ListEntry

TABLE_ID_BYTES: Final = 16
TABLE_ID_PATTERN: Final = "[0-9a-f]{32}"
SERIES_LENGTH_STEP: Final = 3
SERIES_LENGTH_MIN: Final = 3
SERIES_LENGTH_MAX: Final = 99
SERIES_LENGTH_DEFAULT: Final = 36
_TABLE_ID = re.compile(TABLE_ID_PATTERN)


@dataclass(frozen=True)
class OpaqueId:
    """An opaque 128-bit id, written as 32 lower-case hex digits; ids of two kinds are never equal."""

    value: str

    @classmethod
    def random(cls) -> Self:
        return cls(secrets.token_bytes(TABLE_ID_BYTES).hex())

    @classmethod
    def parse(cls, text: str) -> Self | None:
        return cls(text) if _TABLE_ID.fullmatch(text) else None


class OccupantKind(StrEnum):
    """Who sits in a chair: a person, or an agent with its own account; the stored token, also the answer's."""

    PERSON = "person"
    AGENT = "agent"


class TableId(OpaqueId):
    """The id of a table."""


class RuleSetId(OpaqueId):
    """The id of a saved rule set."""


@dataclass(frozen=True)
class Actor:
    """The account behind a request, as the server resolved it; a client never names one.

    `display_name` is the account's name for a person and the name its token carries for an agent.
    """

    account_id: str
    display_name: str
    kind: OccupantKind = OccupantKind.PERSON


@dataclass(frozen=True)
class TableOptions:
    """The rule options a table is opened with; they stay fixed for its life and the default is the official rules.

    `show_running_points` shows everyone the card points each side has taken in completed tricks while a suit or
    Grand game is played. `kontra` makes the table play the words Kontra and Re up to its reach; None plays without.
    `bock` makes the table deal Bock rounds as its triggers and overlap say; None plays without.
    """

    show_running_points: bool = False
    kontra: KontraOptions | None = None
    bock: BockOptions | None = None


@dataclass(frozen=True)
class CreateTable:
    """The command to open a table; `command_id` is the client's key for retrying it, `series_length` the number of
    games its series runs, or None for a table that plays on, and `options` the table's rule options.
    """

    command_id: str
    series_length: int | None = None
    options: TableOptions = TableOptions()


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
    NO_REQUEST = "no-request"
    NO_RESULT = "no-result"
    STALE_RESULT = "stale-result"
    SERIES_OVER = "series-over"
    NO_SERIES = "no-series"
    SERIES_NOT_OVER = "series-not-over"
    NO_GAME_YET = "no-game-yet"
    NO_PROPOSAL = "no-proposal"
    RULE_OFF = "rule-off"


type CommandRefusal = Refusal | BidRefusal | DeclarationRefusal | PlayRefusal | KontraRefusal

# `PlayRefusal` and `KontraRefusal` share their `over` token, and `PlayRefusal` its `not-your-turn`, with `BidRefusal`:
# the wire string is the same either way, and the owner listed last keeps a shared token.
_REFUSALS_BY_TOKEN: Final[dict[str, CommandRefusal]] = {
    refusal.value: refusal for refusal in (*Refusal, *PlayRefusal, *KontraRefusal, *BidRefusal, *DeclarationRefusal)
}


def parsed_refusal(token: str) -> CommandRefusal:
    """The refusal a stored receipt names, whichever owner holds the token; a token nobody owns raises."""
    return _REFUSALS_BY_TOKEN[token]


@dataclass(frozen=True)
class Occupant:
    account_id: str
    display_name: str
    kind: OccupantKind


@dataclass(frozen=True)
class Chair:
    """A chair and who sits on it; `ready` says its occupant is ready for the next hand,
    by a tap of „Weiter“, by sitting down while a result is pending, or, after a series' end, by a tap of
    „Neue Serie“."""

    seat: int
    occupant: Occupant | None
    ready: bool = False


@dataclass(frozen=True)
class GiveUpAsked:
    """A give-up waiting for the other side's yes: who asked, and the opponent who said no."""

    asker: Position
    declined_by: Position | None = None


@dataclass(frozen=True)
class HandProgress:
    """What has happened in the running hand so far; a later phase adds its own field. The words are said beside the
    cards, so each carries how many cards were played before it.

    `give_up` is no step log: a card, the end of the hand or a deal clears it.
    """

    auction: tuple[AuctionStep, ...] = ()
    declaring: tuple[DeclaringStep, ...] = ()
    plays: tuple[CardPlayed, ...] = ()
    give_up: GiveUpAsked | None = None
    words: tuple[WordSaid, ...] = ()


@dataclass(frozen=True)
class EndProposal:
    """A proposal to end the series between games: the seat that proposed it and the one other seat that has accepted
    so far; the second acceptance ends the series, so none holds two.
    """

    proposer: int
    accepter: int | None = None

    def __post_init__(self) -> None:
        if self.accepter == self.proposer:
            message = "the proposer of an end cannot also accept it"
            raise ValueError(message)


@dataclass(frozen=True)
class Series:
    """A table's series: its fixed `length` in games, the `deals` made so far, a passed-in hand included, whether it
    `ended_early` by consent before its last game and the `end_proposal` standing between two games.
    """

    length: int
    deals: int
    ended_early: bool = False
    end_proposal: EndProposal | None = None

    def __post_init__(self) -> None:
        if not SERIES_LENGTH_MIN <= self.length <= SERIES_LENGTH_MAX or self.length % SERIES_LENGTH_STEP:
            message = (
                f"a series length is a multiple of {SERIES_LENGTH_STEP} from {SERIES_LENGTH_MIN} to {SERIES_LENGTH_MAX}"
            )
            raise ValueError(message)
        if not 0 <= self.deals <= self.length:
            message = f"a series of {self.length} games has no {self.deals} deals"
            raise ValueError(message)
        if self.ended_early and self.end_proposal is not None:
            message = "a series that ended early holds no proposal"
            raise ValueError(message)
        if self.ended_early and self.deals == self.length:
            message = "a series that played its last game did not end early"
            raise ValueError(message)


@dataclass(frozen=True)
class TableRecord:
    """A table as stored; its game list outlives every deal of its series and goes with the next series' first deal
    or with the table. `bock` holds the pending Bock rounds, none at a table without Bock and after a series' end."""

    id: TableId
    version: int
    chairs: tuple[Chair, ...]
    dealer: int | None
    hand: Deal | None
    progress: HandProgress
    game_list: tuple[ListEntry, ...]
    series: Series | None
    options: TableOptions
    bock: BockRounds


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
