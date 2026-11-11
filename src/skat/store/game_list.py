from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    SmallInteger,
    Table,
    Text,
    insert,
    select,
    text,
)

from skat.engine.bidding import VALID_BIDS
from skat.engine.deal import SEATS
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
from skat.table.game_list import GameEntry, ListEntry, RamschEntry
from skat.table.rules import CHAIRS_PER_TABLE

if TYPE_CHECKING:
    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

_MOST_MATADORS: Final = max(kind.highest_matadors or 0 for kind in GameKind)
DECLARED_KIND: Final = "declared"
RAMSCH_KIND: Final = "ramsch"
_DECLARED_COLUMNS: Final = (
    "declarer_seat",
    "game",
    "hand",
    "ouvert",
    "announcement",
    "schneider",
    "schwarz",
    "won",
    "bid",
    "game_value",
    "settled_value",
    "score",
    "declarer_points",
)
_RAMSCH_COLUMNS: Final = (
    "seat_1_points",
    "seat_2_points",
    "seat_3_points",
    "seat_1_score",
    "seat_2_score",
    "seat_3_score",
    "jungfrau",
)
_DECLARED_COLUMN_LIST: Final = ", ".join(_DECLARED_COLUMNS)
_RAMSCH_COLUMN_LIST: Final = ", ".join(_RAMSCH_COLUMNS)

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
    Column("declarer_seat", SmallInteger),
    Column("game", Text),
    Column("hand", Boolean),
    Column("ouvert", Boolean),
    Column("announcement", Text),
    Column("schneider", Boolean),
    Column("schwarz", Boolean),
    Column("matadors_mit", Boolean),
    Column("matadors_count", SmallInteger),
    Column("won", Boolean),
    Column("bid", SmallInteger),
    Column("game_value", SmallInteger),
    Column("settled_value", SmallInteger),
    Column("score", Integer),
    Column("declarer_points", SmallInteger),
    Column("kontra_word", Text),
    Column("bock_factor", SmallInteger, nullable=False, server_default=text("1")),
    Column("kind", Text, nullable=False, server_default=text(f"'{DECLARED_KIND}'")),
    Column("seat_1_points", SmallInteger),
    Column("seat_2_points", SmallInteger),
    Column("seat_3_points", SmallInteger),
    Column("seat_1_score", Integer),
    Column("seat_2_score", Integer),
    Column("seat_3_score", Integer),
    Column("durchmarsch_seat", SmallInteger),
    Column("jungfrau", Boolean),
    CheckConstraint("ordinal >= 1", name="game_list_ordinal_counts_from_one"),
    CheckConstraint(f"declarer_seat BETWEEN 1 AND {CHAIRS_PER_TABLE}", name="game_list_declarer_seat_is_a_seat"),
    one_of("game", GAME_TEXT.values(), "game_list_game_is_a_game"),
    one_of("announcement", ANNOUNCEMENT_TEXT.values(), "game_list_announcement_is_an_announcement"),
    one_of("kind", (DECLARED_KIND, RAMSCH_KIND), "game_list_kind_is_a_kind"),
    CheckConstraint(
        f"CASE kind WHEN '{DECLARED_KIND}' THEN num_nonnulls({_DECLARED_COLUMN_LIST}) = {len(_DECLARED_COLUMNS)}"
        f" AND num_nonnulls({_RAMSCH_COLUMN_LIST}, durchmarsch_seat) = 0"
        f" WHEN '{RAMSCH_KIND}' THEN num_nonnulls({_DECLARED_COLUMN_LIST}) = 0"
        f" AND num_nonnulls({_RAMSCH_COLUMN_LIST}) = {len(_RAMSCH_COLUMNS)}"
        " AND num_nonnulls(matadors_mit, matadors_count, kontra_word) = 0 END",
        name="game_list_kind_fills_its_columns",
    ),
    CheckConstraint(
        f"num_nulls(matadors_mit, matadors_count) = CASE WHEN kind = '{RAMSCH_KIND}'"
        f" OR game = '{GAME_TEXT[GameKind.NULL]}' THEN 2 ELSE 0 END",
        name="game_list_matadors_only_outside_null",
    ),
    CheckConstraint(
        " AND ".join(f"seat_{seat}_points BETWEEN 0 AND {ALL_POINTS}" for seat in SEATS),
        name="game_list_ramsch_points_are_card_points",
    ),
    CheckConstraint(f"durchmarsch_seat BETWEEN 1 AND {CHAIRS_PER_TABLE}", name="game_list_durchmarsch_seat_is_a_seat"),
    CheckConstraint(f"matadors_count BETWEEN 1 AND {_MOST_MATADORS}", name="game_list_matadors_count_is_a_count"),
    CheckConstraint(f"bid BETWEEN {VALID_BIDS[0]} AND {VALID_BIDS[-1]}", name="game_list_bid_is_a_bid"),
    CheckConstraint(f"declarer_points BETWEEN 0 AND {ALL_POINTS}", name="game_list_declarer_points_are_card_points"),
    one_of("kontra_word", (word.value for word in Word), "game_list_kontra_word_is_a_word"),
    CheckConstraint(
        "bock_factor > 0 AND bock_factor & (bock_factor - 1) = 0", name="game_list_bock_factor_is_a_power_of_two"
    ),
)


def _ramsch_entry_of(row: Row[tuple[object, ...]]) -> RamschEntry:
    return RamschEntry(
        seat_accounts=(row.seat_1_account, row.seat_2_account, row.seat_3_account),
        seat_names=(row.seat_1_name, row.seat_2_name, row.seat_3_name),
        seat_points=(row.seat_1_points, row.seat_2_points, row.seat_3_points),
        seat_scores=(row.seat_1_score, row.seat_2_score, row.seat_3_score),
        durchmarsch_seat=row.durchmarsch_seat,
        jungfrau=row.jungfrau,
        bock_factor=row.bock_factor,
    )


def _entry_of(row: Row[tuple[object, ...]]) -> GameEntry:
    if row.kind == RAMSCH_KIND:
        return _ramsch_entry_of(row)
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
        bock_factor=row.bock_factor,
    )


def _seats_columns_of(entry: GameEntry) -> dict[str, object]:
    first, second, third = entry.seat_accounts
    first_name, second_name, third_name = entry.seat_names
    return {
        "seat_1_account": first,
        "seat_2_account": second,
        "seat_3_account": third,
        "seat_1_name": first_name,
        "seat_2_name": second_name,
        "seat_3_name": third_name,
    }


def _columns_of(entry: GameEntry) -> dict[str, object]:
    if isinstance(entry, RamschEntry):
        return {
            **_seats_columns_of(entry),
            "kind": RAMSCH_KIND,
            "seat_1_points": entry.seat_points[0],
            "seat_2_points": entry.seat_points[1],
            "seat_3_points": entry.seat_points[2],
            "seat_1_score": entry.seat_scores[0],
            "seat_2_score": entry.seat_scores[1],
            "seat_3_score": entry.seat_scores[2],
            "durchmarsch_seat": entry.durchmarsch_seat,
            "jungfrau": entry.jungfrau,
            "bock_factor": entry.bock_factor,
        }
    matadors = entry.matadors
    return {
        **_seats_columns_of(entry),
        "kind": DECLARED_KIND,
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
        "bock_factor": entry.bock_factor,
    }


def read_game_list(connection: Connection, table_id: str) -> tuple[GameEntry, ...]:
    rows = connection.execute(select(game_list).where(game_list.c.table_id == table_id).order_by(game_list.c.ordinal))
    return tuple(_entry_of(row) for row in rows)


def append_game_list(connection: Connection, table_id: str, entries: tuple[GameEntry, ...]) -> None:
    """Store the entries not yet stored; a stored list that is no prefix of `entries` raises."""
    stored = read_game_list(connection, table_id)
    fresh = unstored_steps(table_id, stored, entries)
    for ordinal, entry in enumerate(fresh, start=len(stored) + 1):
        connection.execute(insert(game_list).values(table_id=table_id, ordinal=ordinal, **_columns_of(entry)))
