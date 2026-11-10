from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, SmallInteger, Table, Text, UniqueConstraint, insert, select

from skat.engine.cards import Card
from skat.engine.tricks import CARDS_IN_A_GAME, CardPlayed
from skat.store.schema import (
    POSITION_OF_TEXT,
    POSITION_TEXT,
    RANK_OF_TEXT,
    RANK_TEXT,
    SUIT_OF_TEXT,
    SUIT_TEXT,
    metadata,
    one_of,
    tables,
    unstored_steps,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

played_cards = Table(
    "played_cards",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("position", Text, nullable=False),
    Column("suit", Text, nullable=False),
    Column("rank", Text, nullable=False),
    UniqueConstraint("table_id", "suit", "rank", name="played_cards_each_card_once"),
    CheckConstraint(f"ordinal BETWEEN 1 AND {CARDS_IN_A_GAME}", name="played_cards_ordinal_is_a_card_of_the_game"),
    one_of("position", POSITION_TEXT.values(), "played_cards_position_is_a_position"),
    one_of("suit", SUIT_TEXT.values(), "played_cards_suit_is_a_suit"),
    one_of("rank", RANK_TEXT.values(), "played_cards_rank_is_a_rank"),
)


def read_plays(connection: Connection, table_id: str) -> tuple[CardPlayed, ...]:
    rows = connection.execute(
        select(played_cards).where(played_cards.c.table_id == table_id).order_by(played_cards.c.ordinal)
    )
    return tuple(
        CardPlayed(POSITION_OF_TEXT[row.position], Card(SUIT_OF_TEXT[row.suit], RANK_OF_TEXT[row.rank])) for row in rows
    )


def append_plays(connection: Connection, table_id: str, plays: tuple[CardPlayed, ...]) -> None:
    """Store the cards not yet stored; stored cards that are no prefix of `plays` raise."""
    stored = read_plays(connection, table_id)
    fresh = unstored_steps(table_id, stored, plays)
    for ordinal, play in enumerate(fresh, start=len(stored) + 1):
        connection.execute(
            insert(played_cards).values(
                table_id=table_id,
                ordinal=ordinal,
                position=POSITION_TEXT[play.position],
                suit=SUIT_TEXT[play.card.suit],
                rank=RANK_TEXT[play.card.rank],
            )
        )
