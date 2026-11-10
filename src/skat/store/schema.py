from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    false,
)

from skat.engine.cards import Rank, Suit
from skat.engine.deal import Position
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind
from skat.table.records import SERIES_LENGTH_MAX, SERIES_LENGTH_MIN, SERIES_LENGTH_STEP, EndReason, OccupantKind

if TYPE_CHECKING:
    from collections.abc import Iterable

metadata = MetaData()


def one_of(column: str, values: Iterable[str], name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN ({', '.join(f"'{value}'" for value in values)})", name=name)


tables = Table(
    "tables",
    metadata,
    Column("id", Text, primary_key=True),
    Column("version", Integer, nullable=False),
    Column("dealer", SmallInteger),
    Column("ended_at", DateTime(timezone=True)),
    Column("end_reason", Text),
    Column("empty_seconds", Integer),
    Column("empty_since", DateTime(timezone=True)),
    Column("series_length", SmallInteger),
    Column("series_deals", SmallInteger),
    Column("show_running_points", Boolean, nullable=False, server_default=false()),
    CheckConstraint("dealer BETWEEN 1 AND 3", name="tables_dealer_is_a_seat"),
    CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="tables_end_time_comes_with_its_reason"),
    CheckConstraint(
        f"(empty_seconds IS NOT NULL) = (end_reason IS NOT DISTINCT FROM '{EndReason.EMPTY.value}')",
        name="tables_empty_seconds_only_for_an_empty_end",
    ),
    CheckConstraint("empty_seconds > 0", name="tables_empty_seconds_are_positive"),
    CheckConstraint("(series_length IS NULL) = (series_deals IS NULL)", name="tables_series_is_both_or_neither"),
    CheckConstraint(
        f"series_length BETWEEN {SERIES_LENGTH_MIN} AND {SERIES_LENGTH_MAX}"
        f" AND series_length % {SERIES_LENGTH_STEP} = 0",
        name="tables_series_length_is_a_length",
    ),
    CheckConstraint("series_deals BETWEEN 0 AND series_length", name="tables_series_deals_are_within_the_length"),
    one_of("end_reason", (reason.value for reason in EndReason), "tables_end_reason_is_a_reason"),
)

chairs = Table(
    "chairs",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("seat", Integer, primary_key=True),
    Column("account_id", Text),
    Column("display_name", Text),
    Column("occupant_kind", Text),
    Column("ready", Boolean, nullable=False, server_default=false()),
    CheckConstraint("account_id IS NOT NULL OR NOT ready", name="chairs_ready_only_when_occupied"),
    CheckConstraint("(account_id IS NULL) = (occupant_kind IS NULL)", name="chairs_kind_only_when_occupied"),
    one_of("occupant_kind", (kind.value for kind in OccupantKind), "chairs_occupant_kind_is_a_kind"),
)

SKAT_HOLDER: Final = "skat"
SUIT_TEXT: Final = {Suit.KARO: "diamonds", Suit.HERZ: "hearts", Suit.PIK: "spades", Suit.KREUZ: "clubs"}
RANK_TEXT: Final = {
    Rank.SEVEN: "seven",
    Rank.EIGHT: "eight",
    Rank.NINE: "nine",
    Rank.TEN: "ten",
    Rank.JACK: "jack",
    Rank.QUEEN: "queen",
    Rank.KING: "king",
    Rank.ACE: "ace",
}
POSITION_TEXT: Final = {
    Position.FOREHAND: "forehand",
    Position.MIDDLEHAND: "middlehand",
    Position.REARHAND: "rearhand",
}
GAME_TEXT: Final = {
    GameKind.KARO: "karo",
    GameKind.HERZ: "herz",
    GameKind.PIK: "pik",
    GameKind.KREUZ: "kreuz",
    GameKind.GRAND: "grand",
    GameKind.NULL: "null",
}
ANNOUNCEMENT_TEXT: Final = {
    Announcement.NONE: "none",
    Announcement.SCHNEIDER: "schneider",
    Announcement.SCHWARZ: "schwarz",
}
SUIT_OF_TEXT: Final = {text: suit for suit, text in SUIT_TEXT.items()}
RANK_OF_TEXT: Final = {text: rank for rank, text in RANK_TEXT.items()}
POSITION_OF_TEXT: Final = {text: position for position, text in POSITION_TEXT.items()}
GAME_OF_TEXT: Final = {text: kind for kind, text in GAME_TEXT.items()}
ANNOUNCEMENT_OF_TEXT: Final = {text: announcement for announcement, text in ANNOUNCEMENT_TEXT.items()}


class StepLogRewrittenError(Exception):
    """The steps being saved do not continue the stored ones: an earlier step would change."""


def unstored_steps[Step](table_id: str, stored: tuple[Step, ...], steps: tuple[Step, ...]) -> tuple[Step, ...]:
    """The steps not yet stored; stored steps that are no prefix of `steps` raise."""
    if steps[: len(stored)] != stored:
        message = f"the steps saved for table {table_id} do not continue the stored ones"
        raise StepLogRewrittenError(message)
    return steps[len(stored) :]


hand_cards = Table(
    "hand_cards",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("suit", Text, primary_key=True),
    Column("rank", Text, primary_key=True),
    Column("holder", Text, nullable=False),
    one_of("suit", SUIT_TEXT.values(), "hand_cards_suit_is_a_suit"),
    one_of("rank", RANK_TEXT.values(), "hand_cards_rank_is_a_rank"),
    one_of("holder", (*POSITION_TEXT.values(), SKAT_HOLDER), "hand_cards_holder_is_a_holder"),
)

receipts = Table(
    "receipts",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("command_id", Text, primary_key=True),
    Column("command", Text, nullable=False),
    Column("payload", Text, nullable=False),
    Column("table_id", Text, nullable=False),
    Column("refusal", Text),
    Column("holder", Text),
    ForeignKeyConstraint(["table_id"], [tables.c.id]),
)
