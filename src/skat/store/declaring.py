from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, SmallInteger, Table, Text, insert, select

from skat.engine.cards import Card, Rank, Suit
from skat.engine.declaration import Announcement, Declare, DeclaringStep, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.store.schema import RANK_TEXT, SUIT_TEXT, metadata, one_of, tables, unstored_steps

if TYPE_CHECKING:
    from sqlalchemy import Row
    from sqlalchemy.engine import Connection


class _Action(StrEnum):
    TAKE = "take"
    PUT_BACK = "put-back"
    DECLARE = "declare"


_GAME_TEXT: Final = {
    GameKind.KARO: "karo",
    GameKind.HERZ: "herz",
    GameKind.PIK: "pik",
    GameKind.KREUZ: "kreuz",
    GameKind.GRAND: "grand",
    GameKind.NULL: "null",
}
_KIND_OF_TEXT: Final = {text: kind for kind, text in _GAME_TEXT.items()}
_SUIT_OF_TEXT: Final[dict[str, Suit]] = {text: suit for suit, text in SUIT_TEXT.items()}
_RANK_OF_TEXT: Final[dict[str, Rank]] = {text: rank for rank, text in RANK_TEXT.items()}

declaring_steps = Table(
    "declaring_steps",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("action", Text, nullable=False),
    Column("first_suit", Text),
    Column("first_rank", Text),
    Column("second_suit", Text),
    Column("second_rank", Text),
    Column("game", Text),
    Column("hand", Boolean),
    Column("ouvert", Boolean),
    Column("announcement", Text),
    CheckConstraint("ordinal BETWEEN 1 AND 3", name="declaring_steps_ordinal_is_a_step"),
    one_of("action", (action.value for action in _Action), "declaring_steps_action_is_an_action"),
    one_of("first_suit", SUIT_TEXT.values(), "declaring_steps_first_suit_is_a_suit"),
    one_of("first_rank", RANK_TEXT.values(), "declaring_steps_first_rank_is_a_rank"),
    one_of("second_suit", SUIT_TEXT.values(), "declaring_steps_second_suit_is_a_suit"),
    one_of("second_rank", RANK_TEXT.values(), "declaring_steps_second_rank_is_a_rank"),
    one_of("game", _GAME_TEXT.values(), "declaring_steps_game_is_a_game"),
    one_of(
        "announcement",
        (announcement.value for announcement in Announcement),
        "declaring_steps_announcement_is_an_announcement",
    ),
    CheckConstraint(
        "num_nonnulls(first_suit, first_rank, second_suit, second_rank) "
        f"= CASE WHEN action = '{_Action.PUT_BACK.value}' THEN 4 ELSE 0 END",
        name="declaring_steps_cards_only_on_a_put_back",
    ),
    CheckConstraint(
        "(first_suit, first_rank) <> (second_suit, second_rank)", name="declaring_steps_the_two_cards_differ"
    ),
    CheckConstraint(
        "num_nonnulls(game, hand, ouvert, announcement) "
        f"= CASE WHEN action = '{_Action.DECLARE.value}' THEN 4 ELSE 0 END",
        name="declaring_steps_game_only_on_a_declare",
    ),
)


def _card_of(suit: str, rank: str) -> Card:
    return Card(_SUIT_OF_TEXT[suit], _RANK_OF_TEXT[rank])


def _step_of(row: Row[tuple[str, ...]]) -> DeclaringStep:
    action = _Action(row.action)
    if action is _Action.TAKE:
        return TakeSkat()
    if action is _Action.PUT_BACK:
        return PutBack((_card_of(row.first_suit, row.first_rank), _card_of(row.second_suit, row.second_rank)))
    return Declare(
        _KIND_OF_TEXT[row.game],
        hand=row.hand,
        ouvert=row.ouvert,
        announcement=Announcement(row.announcement),
    )


def _columns_of(step: DeclaringStep) -> dict[str, object]:
    if isinstance(step, TakeSkat):
        return {"action": _Action.TAKE.value}
    if isinstance(step, PutBack):
        first, second = step.cards
        return {
            "action": _Action.PUT_BACK.value,
            "first_suit": SUIT_TEXT[first.suit],
            "first_rank": RANK_TEXT[first.rank],
            "second_suit": SUIT_TEXT[second.suit],
            "second_rank": RANK_TEXT[second.rank],
        }
    return {
        "action": _Action.DECLARE.value,
        "game": _GAME_TEXT[step.kind],
        "hand": step.hand,
        "ouvert": step.ouvert,
        "announcement": step.announcement.value,
    }


def read_declaring_steps(connection: Connection, table_id: str) -> tuple[DeclaringStep, ...]:
    rows = connection.execute(
        select(declaring_steps).where(declaring_steps.c.table_id == table_id).order_by(declaring_steps.c.ordinal)
    )
    return tuple(_step_of(row) for row in rows)


def append_declaring_steps(connection: Connection, table_id: str, steps: tuple[DeclaringStep, ...]) -> None:
    """Store the steps not yet stored; stored steps that are no prefix of `steps` raise."""
    stored = read_declaring_steps(connection, table_id)
    fresh = unstored_steps(table_id, stored, steps)
    for ordinal, step in enumerate(fresh, start=len(stored) + 1):
        connection.execute(insert(declaring_steps).values(table_id=table_id, ordinal=ordinal, **_columns_of(step)))
