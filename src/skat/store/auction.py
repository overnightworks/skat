from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, SmallInteger, Table, Text, delete, insert, select

from skat.engine.bidding import VALID_BIDS, Bid
from skat.store.schema import POSITION_OF_TEXT, POSITION_TEXT, metadata, one_of, tables, unstored_steps
from skat.table.auction import AuctionAction, action_of, step_of

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from skat.engine.bidding import AuctionStep

auction_actions = Table(
    "auction_actions",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("position", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("value", SmallInteger),
    one_of("position", POSITION_TEXT.values(), "auction_actions_position_is_a_position"),
    one_of("action", (action.value for action in AuctionAction), "auction_actions_action_is_an_action"),
    CheckConstraint(
        f"(action = '{AuctionAction.BID.value}') = (value IS NOT NULL)", name="auction_actions_value_only_on_a_bid"
    ),
    CheckConstraint(f"value BETWEEN {VALID_BIDS[0]} AND {VALID_BIDS[-1]}", name="auction_actions_value_is_a_bid"),
)


def read_steps(connection: Connection, table_id: str) -> tuple[AuctionStep, ...]:
    rows = connection.execute(
        select(auction_actions.c.position, auction_actions.c.action, auction_actions.c.value)
        .where(auction_actions.c.table_id == table_id)
        .order_by(auction_actions.c.ordinal)
    )
    return tuple(step_of(AuctionAction(row.action), row.value, POSITION_OF_TEXT[row.position]) for row in rows)


def delete_steps(connection: Connection, table_id: str) -> None:
    """Forget the steps of the hand before; only a new hand's write calls this."""
    connection.execute(delete(auction_actions).where(auction_actions.c.table_id == table_id))


def append_steps(connection: Connection, table_id: str, steps: tuple[AuctionStep, ...]) -> None:
    """Store the steps not yet stored; stored steps that are no prefix of `steps` raise."""
    stored = read_steps(connection, table_id)
    fresh = unstored_steps(table_id, stored, steps)
    if fresh:
        connection.execute(
            insert(auction_actions),
            [
                {
                    "table_id": table_id,
                    "ordinal": ordinal,
                    "position": POSITION_TEXT[step.position],
                    "action": action_of(step).value,
                    "value": step.value if isinstance(step, Bid) else None,
                }
                for ordinal, step in enumerate(fresh, start=len(stored) + 1)
            ],
        )
