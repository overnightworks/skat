from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    Table,
    Text,
    insert,
    select,
    text,
)

from skat.engine.bidding import VALID_BIDS
from skat.engine.cards import Card
from skat.engine.deal import SEATS, Position
from skat.engine.declaration import Declaration
from skat.engine.games import GameKind
from skat.engine.kontra import Word
from skat.engine.tricks import ALL_POINTS, TRICKS_IN_A_GAME
from skat.engine.value import Matadors
from skat.store.schema import (
    ANNOUNCEMENT_OF_TEXT,
    ANNOUNCEMENT_TEXT,
    GAME_OF_TEXT,
    GAME_TEXT,
    RANK_OF_TEXT,
    RANK_TEXT,
    SUIT_OF_TEXT,
    SUIT_TEXT,
    metadata,
    one_of,
    tables,
    unstored_steps,
)
from skat.table.game_cards import GameCards, SeatedCard, in_deck_order, put_away_in_order
from skat.table.game_list import GameEnding, GameEntry, ListEntry, RamschEntry
from skat.table.rules import CHAIRS_PER_TABLE

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

# Each of the three seats may push the skat on once.
_MOST_PUSHES: Final = len(Position)
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
    Column("series_number", SmallInteger, primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("finished_at", DateTime(timezone=True)),
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
    Column("ending", Text, nullable=False, server_default=text(f"'{GameEnding.PLAYED_OUT.value}'")),
    Column("ended_by_seat", SmallInteger),
    Column("pushes", SmallInteger, nullable=False, server_default=text("0")),
    CheckConstraint("series_number >= 1", name="game_list_series_number_counts_from_one"),
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
    one_of("ending", (ending.value for ending in GameEnding), "game_list_ending_is_an_ending"),
    CheckConstraint(f"ended_by_seat BETWEEN 1 AND {CHAIRS_PER_TABLE}", name="game_list_ended_by_seat_is_a_seat"),
    CheckConstraint(
        f"(ending = '{GameEnding.PLAYED_OUT.value}') = (ended_by_seat IS NULL)",
        name="game_list_a_seat_ends_exactly_an_unplayed_game",
    ),
    CheckConstraint(
        f"kind <> '{RAMSCH_KIND}' OR ending = '{GameEnding.PLAYED_OUT.value}'", name="game_list_a_ramsch_is_played_out"
    ),
    CheckConstraint(f"durchmarsch_seat BETWEEN 1 AND {CHAIRS_PER_TABLE}", name="game_list_durchmarsch_seat_is_a_seat"),
    CheckConstraint(f"matadors_count BETWEEN 1 AND {_MOST_MATADORS}", name="game_list_matadors_count_is_a_count"),
    CheckConstraint(f"bid BETWEEN {VALID_BIDS[0]} AND {VALID_BIDS[-1]}", name="game_list_bid_is_a_bid"),
    CheckConstraint(f"declarer_points BETWEEN 0 AND {ALL_POINTS}", name="game_list_declarer_points_are_card_points"),
    one_of("kontra_word", (word.value for word in Word), "game_list_kontra_word_is_a_word"),
    CheckConstraint(
        "bock_factor > 0 AND bock_factor & (bock_factor - 1) = 0", name="game_list_bock_factor_is_a_power_of_two"
    ),
    CheckConstraint(f"pushes BETWEEN 0 AND {_MOST_PUSHES}", name="game_list_pushes_are_unseen_pushes"),
    CheckConstraint(f"kind = '{RAMSCH_KIND}' OR pushes = 0", name="game_list_only_a_ramsch_is_pushed"),
)


class Pile(StrEnum):
    """Where a stored card lay: in a seat's hand as dealt, in the skat as dealt, put away by a seat or in a
    trick.
    """

    HAND = "hand"
    SKAT = "skat"
    PUT_AWAY = "put-away"
    TRICK = "trick"


_CARDS_PER_TRICK: Final = len(Position)
_SHAPE_OF_A_PILE: Final = {
    Pile.HAND: "seat IS NOT NULL AND trick IS NULL AND place IS NULL",
    Pile.SKAT: "seat IS NULL AND trick IS NULL AND place IS NULL",
    Pile.PUT_AWAY: "seat IS NOT NULL AND trick IS NULL AND place IS NULL",
    Pile.TRICK: "seat IS NOT NULL AND trick IS NOT NULL AND place IS NOT NULL",
}
_DEALT_PILES: Final = f"pile IN ('{Pile.HAND.value}', '{Pile.SKAT.value}')"

# A card has no row of its own: a game stores each card once per pile it lay in, and a pile's shape says which of
# the seat, the trick and the place it names.
game_cards = Table(
    "game_cards",
    metadata,
    Column("table_id", Text, nullable=False),
    Column("series_number", SmallInteger, nullable=False),
    Column("ordinal", SmallInteger, nullable=False),
    Column("pile", Text, nullable=False),
    Column("seat", SmallInteger),
    Column("trick", SmallInteger),
    Column("place", SmallInteger),
    Column("suit", Text, nullable=False),
    Column("rank", Text, nullable=False),
    ForeignKeyConstraint(
        ["table_id", "series_number", "ordinal"],
        [game_list.c.table_id, game_list.c.series_number, game_list.c.ordinal],
    ),
    one_of("pile", (pile.value for pile in Pile), "game_cards_pile_is_a_pile"),
    CheckConstraint(f"seat BETWEEN 1 AND {CHAIRS_PER_TABLE}", name="game_cards_seat_is_a_seat"),
    CheckConstraint(f"trick BETWEEN 1 AND {TRICKS_IN_A_GAME}", name="game_cards_trick_is_a_trick_of_the_game"),
    CheckConstraint(f"place BETWEEN 1 AND {_CARDS_PER_TRICK}", name="game_cards_place_is_a_place_in_a_trick"),
    one_of("suit", SUIT_TEXT.values(), "game_cards_suit_is_a_suit"),
    one_of("rank", RANK_TEXT.values(), "game_cards_rank_is_a_rank"),
    CheckConstraint(
        "CASE pile "
        + " ".join(f"WHEN '{pile.value}' THEN {shape}" for pile, shape in _SHAPE_OF_A_PILE.items())
        + " END",
        name="game_cards_a_pile_names_what_it_is_in",
    ),
    Index(
        "game_cards_each_card_dealt_once",
        "table_id",
        "series_number",
        "ordinal",
        "suit",
        "rank",
        unique=True,
        postgresql_where=text(_DEALT_PILES),
    ),
    Index(
        "game_cards_each_card_played_once",
        "table_id",
        "series_number",
        "ordinal",
        "suit",
        "rank",
        unique=True,
        postgresql_where=text(f"pile = '{Pile.TRICK.value}'"),
    ),
    Index(
        "game_cards_each_place_taken_once",
        "table_id",
        "series_number",
        "ordinal",
        "trick",
        "place",
        unique=True,
        postgresql_where=text(f"pile = '{Pile.TRICK.value}'"),
    ),
    Index(
        "game_cards_a_seat_puts_a_card_away_once",
        "table_id",
        "series_number",
        "ordinal",
        "seat",
        "suit",
        "rank",
        unique=True,
        postgresql_where=text(f"pile = '{Pile.PUT_AWAY.value}'"),
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
        pushes=row.pushes,
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
        ending=GameEnding(row.ending),
        ended_by_seat=row.ended_by_seat,
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
            "pushes": entry.pushes,
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
        "ending": entry.ending.value,
        "ended_by_seat": entry.ended_by_seat,
    }


def read_game_list(connection: Connection, table_id: str) -> tuple[GameEntry, ...]:
    """The games of the table's current series, the series number its row holds."""
    current_series = select(tables.c.series_number).where(tables.c.id == table_id).scalar_subquery()
    rows = connection.execute(
        select(game_list)
        .where(game_list.c.table_id == table_id, game_list.c.series_number == current_series)
        .order_by(game_list.c.ordinal)
    )
    return tuple(_entry_of(row) for row in rows)


def _card_row(
    pile: Pile, card: Card, seat: int | None = None, trick: int | None = None, place: int | None = None
) -> dict[str, object]:
    return {
        "pile": pile.value,
        "seat": seat,
        "trick": trick,
        "place": place,
        "suit": SUIT_TEXT[card.suit],
        "rank": RANK_TEXT[card.rank],
    }


def _card_rows_of(cards: GameCards) -> list[dict[str, object]]:
    return [
        *(_card_row(Pile.HAND, card, seat) for seat, hand in enumerate(cards.hands, start=1) for card in hand),
        *(_card_row(Pile.SKAT, card) for card in cards.skat),
        *(_card_row(Pile.PUT_AWAY, put.card, put.seat) for put in cards.put_away),
        *(
            _card_row(Pile.TRICK, played.card, played.seat, number, place)
            for number, trick in enumerate(cards.tricks, start=1)
            for place, played in enumerate(trick, start=1)
        ),
    ]


def _cards_of(rows: Iterable[Row[tuple[object, ...]]]) -> GameCards:
    """The game's cards from its rows, each pile in the order the record keeps it."""
    hands: dict[int, list[Card]] = {seat: [] for seat in SEATS}
    skat: list[Card] = []
    put_away: list[SeatedCard] = []
    tricks: dict[int, list[SeatedCard]] = {}
    for row in sorted(rows, key=lambda each: (each.trick or 0, each.place or 0)):
        card = Card(SUIT_OF_TEXT[row.suit], RANK_OF_TEXT[row.rank])
        match Pile(row.pile):
            case Pile.HAND:
                hands[row.seat].append(card)
            case Pile.SKAT:
                skat.append(card)
            case Pile.PUT_AWAY:
                put_away.append(SeatedCard(row.seat, card))
            case _:  # the trick pile, the last of the four
                tricks.setdefault(row.trick, []).append(SeatedCard(row.seat, card))
    first, second, third = (in_deck_order(hands[seat]) for seat in SEATS)
    return GameCards(
        hands=(first, second, third),
        skat=in_deck_order(skat),
        put_away=put_away_in_order(put_away),
        tricks=tuple(tuple(tricks[number]) for number in sorted(tricks)),
    )


def read_game_cards(connection: Connection, table_id: str, number: int) -> GameCards | None:
    """The cards of the `number`th game of the table's current series; None for a game stored without them."""
    current_series = select(tables.c.series_number).where(tables.c.id == table_id).scalar_subquery()
    rows = connection.execute(
        select(game_cards).where(
            game_cards.c.table_id == table_id,
            game_cards.c.series_number == current_series,
            game_cards.c.ordinal == number,
        )
    ).all()
    return _cards_of(rows) if rows else None


def append_game_list(
    connection: Connection,
    table_id: str,
    series_number: int,
    entries: tuple[GameEntry, ...],
    finished_at: datetime | None,
) -> None:
    """Store the entries of the current series not yet stored, each as finished at `finished_at` with the cards it
    carries; a stored list that is no prefix of `entries` raises.
    """
    stored = read_game_list(connection, table_id)
    fresh = unstored_steps(table_id, stored, entries)
    for ordinal, entry in enumerate(fresh, start=len(stored) + 1):
        key = {"table_id": table_id, "series_number": series_number, "ordinal": ordinal}
        connection.execute(insert(game_list).values(**key, finished_at=finished_at, **_columns_of(entry)))
        if entry.cards is not None:
            connection.execute(insert(game_cards), [{**key, **row} for row in _card_rows_of(entry.cards)])
