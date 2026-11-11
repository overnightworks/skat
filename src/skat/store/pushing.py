from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, SmallInteger, Table, Text, insert, select

from skat.engine.cards import Card
from skat.engine.deal import Position
from skat.engine.schieberamsch import Push, Put, Take
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
    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

    from skat.table.records import PushingStep

# A take and a put-back, or a push, for each seat.
MOST_PUSHING_STEPS = 2 * len(Position)


class _Action(StrEnum):
    TAKE = "take"
    PUT_BACK = "put-back"
    PUSH = "push"


pushing_steps = Table(
    "pushing_steps",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("position", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("first_suit", Text),
    Column("first_rank", Text),
    Column("second_suit", Text),
    Column("second_rank", Text),
    CheckConstraint(f"ordinal BETWEEN 1 AND {MOST_PUSHING_STEPS}", name="pushing_steps_ordinal_is_a_step"),
    one_of("position", POSITION_TEXT.values(), "pushing_steps_position_is_a_position"),
    one_of("action", (action.value for action in _Action), "pushing_steps_action_is_an_action"),
    one_of("first_suit", SUIT_TEXT.values(), "pushing_steps_first_suit_is_a_suit"),
    one_of("first_rank", RANK_TEXT.values(), "pushing_steps_first_rank_is_a_rank"),
    one_of("second_suit", SUIT_TEXT.values(), "pushing_steps_second_suit_is_a_suit"),
    one_of("second_rank", RANK_TEXT.values(), "pushing_steps_second_rank_is_a_rank"),
    CheckConstraint(
        "num_nonnulls(first_suit, first_rank, second_suit, second_rank) "
        f"= CASE WHEN action = '{_Action.PUT_BACK.value}' THEN 4 ELSE 0 END",
        name="pushing_steps_cards_only_on_a_put_back",
    ),
    CheckConstraint(
        "(first_suit, first_rank) <> (second_suit, second_rank)", name="pushing_steps_the_two_cards_differ"
    ),
)


def _card_of(suit: str, rank: str) -> Card:
    return Card(SUIT_OF_TEXT[suit], RANK_OF_TEXT[rank])


def _step_of(row: Row[tuple[str, ...]]) -> PushingStep:
    position = POSITION_OF_TEXT[row.position]
    action = _Action(row.action)
    if action is _Action.TAKE:
        return Take(position)
    if action is _Action.PUSH:
        return Push(position)
    return Put(position, (_card_of(row.first_suit, row.first_rank), _card_of(row.second_suit, row.second_rank)))


def _columns_of(step: PushingStep) -> dict[str, object]:
    position = {"position": POSITION_TEXT[step.position]}
    if isinstance(step, Take):
        return {**position, "action": _Action.TAKE.value}
    if isinstance(step, Push):
        return {**position, "action": _Action.PUSH.value}
    first, second = step.cards
    return {
        **position,
        "action": _Action.PUT_BACK.value,
        "first_suit": SUIT_TEXT[first.suit],
        "first_rank": RANK_TEXT[first.rank],
        "second_suit": SUIT_TEXT[second.suit],
        "second_rank": RANK_TEXT[second.rank],
    }


def read_pushing_steps(connection: Connection, table_id: str) -> tuple[PushingStep, ...]:
    rows = connection.execute(
        select(pushing_steps).where(pushing_steps.c.table_id == table_id).order_by(pushing_steps.c.ordinal)
    )
    return tuple(_step_of(row) for row in rows)


def append_pushing_steps(connection: Connection, table_id: str, steps: tuple[PushingStep, ...]) -> None:
    """Store the steps not yet stored; stored steps that are no prefix of `steps` raise."""
    stored = read_pushing_steps(connection, table_id)
    fresh = unstored_steps(table_id, stored, steps)
    for ordinal, step in enumerate(fresh, start=len(stored) + 1):
        connection.execute(insert(pushing_steps).values(table_id=table_id, ordinal=ordinal, **_columns_of(step)))
