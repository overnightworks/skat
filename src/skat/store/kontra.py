from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, SmallInteger, Table, Text, delete, insert, select

from skat.engine.kontra import Word, WordSaid
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.store.schema import POSITION_OF_TEXT, POSITION_TEXT, metadata, one_of, tables, unstored_steps
from skat.table.records import NoWordSaid

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

WORDS_IN_A_HAND = len(Word)

kontra_words = Table(
    "kontra_words",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("position", Text, nullable=False),
    Column("word", Text, nullable=False),
    Column("cards_before", SmallInteger, nullable=False),
    CheckConstraint(f"ordinal BETWEEN 1 AND {WORDS_IN_A_HAND}", name="kontra_words_ordinal_is_a_word_of_the_hand"),
    CheckConstraint(
        f"cards_before BETWEEN 0 AND {CARDS_IN_A_GAME - 1}", name="kontra_words_cards_before_are_cards_of_the_game"
    ),
    one_of("position", POSITION_TEXT.values(), "kontra_words_position_is_a_position"),
    one_of("word", (word.value for word in Word), "kontra_words_word_is_a_word"),
)

kontra_no_words = Table(
    "kontra_no_words",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("position", Text, primary_key=True),
    Column("word", Text, primary_key=True),
    one_of("position", POSITION_TEXT.values(), "kontra_no_words_position_is_a_position"),
    one_of("word", (word.value for word in Word), "kontra_no_words_word_is_a_word"),
)


def read_words(connection: Connection, table_id: str) -> tuple[WordSaid, ...]:
    rows = connection.execute(
        select(kontra_words).where(kontra_words.c.table_id == table_id).order_by(kontra_words.c.ordinal)
    )
    return tuple(WordSaid(POSITION_OF_TEXT[row.position], Word(row.word), row.cards_before) for row in rows)


def append_words(connection: Connection, table_id: str, words: tuple[WordSaid, ...]) -> None:
    """Store the words not yet stored; stored words that are no prefix of `words` raise."""
    stored = read_words(connection, table_id)
    fresh = unstored_steps(table_id, stored, words)
    for ordinal, said in enumerate(fresh, start=len(stored) + 1):
        connection.execute(
            insert(kontra_words).values(
                table_id=table_id,
                ordinal=ordinal,
                position=POSITION_TEXT[said.position],
                word=said.word.value,
                cards_before=said.cards_before,
            )
        )


def read_no_words(connection: Connection, table_id: str) -> frozenset[NoWordSaid]:
    rows = connection.execute(select(kontra_no_words).where(kontra_no_words.c.table_id == table_id))
    return frozenset(NoWordSaid(POSITION_OF_TEXT[row.position], Word(row.word)) for row in rows)


def write_no_words(connection: Connection, table_id: str, no_words: frozenset[NoWordSaid]) -> None:
    """Store the answers of no word so that exactly `no_words` stay."""
    stored = read_no_words(connection, table_id)
    for gone in stored - no_words:
        connection.execute(
            delete(kontra_no_words).where(
                kontra_no_words.c.table_id == table_id,
                kontra_no_words.c.position == POSITION_TEXT[gone.position],
                kontra_no_words.c.word == gone.word.value,
            )
        )
    for fresh in no_words - stored:
        connection.execute(
            insert(kontra_no_words).values(
                table_id=table_id, position=POSITION_TEXT[fresh.position], word=fresh.word.value
            )
        )
