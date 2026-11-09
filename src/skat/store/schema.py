from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
)

from skat.engine.cards import Rank, Suit
from skat.engine.deal import Position
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind

if TYPE_CHECKING:
    from collections.abc import Iterable

metadata = MetaData()


tables = Table(
    "tables",
    metadata,
    Column("id", Text, primary_key=True),
    Column("version", Integer, nullable=False),
    Column("dealer", SmallInteger),
    CheckConstraint("dealer BETWEEN 1 AND 3", name="tables_dealer_is_a_seat"),
)

chairs = Table(
    "chairs",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("seat", Integer, primary_key=True),
    Column("account_id", Text),
    Column("display_name", Text),
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


def one_of(column: str, values: Iterable[str], name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN ({', '.join(f"'{value}'" for value in values)})", name=name)


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
