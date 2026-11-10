from typing import TYPE_CHECKING, Final

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, SmallInteger, Table, Text, insert, select

from skat.engine.bidding import VALID_BIDS
from skat.engine.declaration import Declaration
from skat.engine.games import GameKind
from skat.engine.kontra import Word
from skat.engine.tricks import ALL_POINTS
from skat.engine.value import Matadors
from skat.store.schema import (
    ANNOUNCEMENT_OF_TEXT,
    ANNOUNCEMENT_TEXT,
    GAME_OF_TEXT,
    GAME_TEXT,
    metadata,
    one_of,
    tables,
    unstored_steps,
)
from skat.table.game_list import ListEntry
from skat.table.rules import CHAIRS_PER_TABLE

if TYPE_CHECKING:
    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

_MOST_MATADORS: Final = max(kind.highest_matadors or 0 for kind in GameKind)

game_list = Table(
    "game_list",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("seat_1_account", Text, nullable=False),
    Column("seat_2_account", Text, nullable=False),
    Column("seat_3_account", Text, nullable=False),
    Column("seat_1_name", Text),
    Column("seat_2_name", Text),
    Column("seat_3_name", Text),
    Column("declarer_seat", SmallInteger, nullable=False),
    Column("game", Text, nullable=False),
    Column("hand", Boolean, nullable=False),
    Column("ouvert", Boolean, nullable=False),
    Column("announcement", Text, nullable=False),
    Column("schneider", Boolean, nullable=False),
    Column("schwarz", Boolean, nullable=False),
    Column("matadors_mit", Boolean),
    Column("matadors_count", SmallInteger),
    Column("won", Boolean, nullable=False),
    Column("bid", SmallInteger, nullable=False),
    Column("game_value", SmallInteger, nullable=False),
    Column("settled_value", SmallInteger, nullable=False),
    Column("score", SmallInteger, nullable=False),
    Column("declarer_points", SmallInteger, nullable=False),
    Column("kontra_word", Text),
    CheckConstraint("ordinal >= 1", name="game_list_ordinal_counts_from_one"),
    CheckConstraint(f"declarer_seat BETWEEN 1 AND {CHAIRS_PER_TABLE}", name="game_list_declarer_seat_is_a_seat"),
    one_of("game", GAME_TEXT.values(), "game_list_game_is_a_game"),
    one_of("announcement", ANNOUNCEMENT_TEXT.values(), "game_list_announcement_is_an_announcement"),
    CheckConstraint(
        f"num_nulls(matadors_mit, matadors_count) = CASE WHEN game = '{GAME_TEXT[GameKind.NULL]}' THEN 2 ELSE 0 END",
        name="game_list_matadors_only_outside_null",
    ),
    CheckConstraint(f"matadors_count BETWEEN 1 AND {_MOST_MATADORS}", name="game_list_matadors_count_is_a_count"),
    CheckConstraint(f"bid BETWEEN {VALID_BIDS[0]} AND {VALID_BIDS[-1]}", name="game_list_bid_is_a_bid"),
    CheckConstraint(f"declarer_points BETWEEN 0 AND {ALL_POINTS}", name="game_list_declarer_points_are_card_points"),
    one_of("kontra_word", (word.value for word in Word), "game_list_kontra_word_is_a_word"),
)


def _entry_of(row: Row[tuple[object, ...]]) -> ListEntry:
    return ListEntry(
        seat_accounts=(row.seat_1_account, row.seat_2_account, row.seat_3_account),
        seat_names=(row.seat_1_name, row.seat_2_name, row.seat_3_name),
        declarer_seat=row.declarer_seat,
        declaration=Declaration(
            GAME_OF_TEXT[row.game],
            hand=row.hand,
            ouvert=row.ouvert,
            announcement=ANNOUNCEMENT_OF_TEXT[row.announcement],
        ),
        schneider=row.schneider,
        schwarz=row.schwarz,
        matadors=None if row.matadors_mit is None else Matadors(mit=row.matadors_mit, count=row.matadors_count),
        won=row.won,
        bid=row.bid,
        game_value=row.game_value,
        settled_value=row.settled_value,
        score=row.score,
        declarer_points=row.declarer_points,
        kontra_word=None if row.kontra_word is None else Word(row.kontra_word),
    )


def _columns_of(entry: ListEntry) -> dict[str, object]:
    first, second, third = entry.seat_accounts
    first_name, second_name, third_name = entry.seat_names
    matadors = entry.matadors
    return {
        "seat_1_account": first,
        "seat_2_account": second,
        "seat_3_account": third,
        "seat_1_name": first_name,
        "seat_2_name": second_name,
        "seat_3_name": third_name,
        "declarer_seat": entry.declarer_seat,
        "game": GAME_TEXT[entry.declaration.kind],
        "hand": entry.declaration.hand,
        "ouvert": entry.declaration.ouvert,
        "announcement": ANNOUNCEMENT_TEXT[entry.declaration.announcement],
        "schneider": entry.schneider,
        "schwarz": entry.schwarz,
        "matadors_mit": None if matadors is None else matadors.mit,
        "matadors_count": None if matadors is None else matadors.count,
        "won": entry.won,
        "bid": entry.bid,
        "game_value": entry.game_value,
        "settled_value": entry.settled_value,
        "score": entry.score,
        "declarer_points": entry.declarer_points,
        "kontra_word": None if entry.kontra_word is None else entry.kontra_word.value,
    }


def read_game_list(connection: Connection, table_id: str) -> tuple[ListEntry, ...]:
    rows = connection.execute(select(game_list).where(game_list.c.table_id == table_id).order_by(game_list.c.ordinal))
    return tuple(_entry_of(row) for row in rows)


def append_game_list(connection: Connection, table_id: str, entries: tuple[ListEntry, ...]) -> None:
    """Store the entries not yet stored; a stored list that is no prefix of `entries` raises."""
    stored = read_game_list(connection, table_id)
    fresh = unstored_steps(table_id, stored, entries)
    for ordinal, entry in enumerate(fresh, start=len(stored) + 1):
        connection.execute(insert(game_list).values(table_id=table_id, ordinal=ordinal, **_columns_of(entry)))
