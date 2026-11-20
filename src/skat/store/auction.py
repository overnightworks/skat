from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    Table,
    Text,
    delete,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import insert as upsert

from skat.engine.bidding import VALID_BIDS, Bid
from skat.store.schema import POSITION_OF_TEXT, POSITION_TEXT, chairs, metadata, one_of, tables, unstored_steps
from skat.table.auction import AuctionAction, action_of, step_of
from skat.table.records import AuctionPlan, BidLimit, PassAhead, PlanMode, SeatPlan

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from skat.engine.bidding import AuctionStep
    from skat.table.records import TableRecord

LIMIT_KIND: Final = "limit"
PASS_KIND: Final = "pass"

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

# A seat's private plan for the auction, with the account that made it: it is read only while that account still sits
# in the chair, since the release before frees a chair without naming this table, and it goes with the chair. A deal of
# that release clears it through a trigger that migration 0057 creates.
auction_plans = Table(
    "auction_plans",
    metadata,
    Column("table_id", Text, primary_key=True),
    Column("seat", Integer, primary_key=True),
    Column("account_id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("value", SmallInteger),
    Column("mode", Text),
    ForeignKeyConstraint(["table_id", "seat"], [chairs.c.table_id, chairs.c.seat], ondelete="CASCADE"),
    one_of("kind", (LIMIT_KIND, PASS_KIND), "auction_plans_kind_is_a_kind"),
    one_of("mode", (mode.value for mode in PlanMode), "auction_plans_mode_is_a_mode"),
    CheckConstraint(
        f"(kind = '{LIMIT_KIND}') = (value IS NOT NULL AND mode IS NOT NULL)",
        name="auction_plans_a_limit_has_a_value_and_a_mode",
    ),
    CheckConstraint(
        f"(kind = '{PASS_KIND}') = (value IS NULL AND mode IS NULL)",
        name="auction_plans_a_pass_has_no_value_and_no_mode",
    ),
    CheckConstraint(f"value IN ({', '.join(map(str, VALID_BIDS))})", name="auction_plans_value_is_a_bid"),
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


def _plan_of(kind: str, value: int | None, mode: str | None) -> AuctionPlan:
    if kind == PASS_KIND or value is None or mode is None:
        return PassAhead()
    return BidLimit(value, PlanMode(mode))


def read_plans(connection: Connection, table_id: str) -> frozenset[SeatPlan]:
    """The plans of the seats whose account still sits in the chair."""
    rows = connection.execute(
        select(auction_plans.c.seat, auction_plans.c.kind, auction_plans.c.value, auction_plans.c.mode)
        .join(
            chairs,
            (chairs.c.table_id == auction_plans.c.table_id)
            & (chairs.c.seat == auction_plans.c.seat)
            & (chairs.c.account_id == auction_plans.c.account_id),
        )
        .where(auction_plans.c.table_id == table_id)
    )
    return frozenset(SeatPlan(row.seat, _plan_of(row.kind, row.value, row.mode)) for row in rows)


def write_plans(connection: Connection, table: TableRecord) -> None:
    """Make the stored plans the record's: a seat without a plan loses its row."""
    wanted = {each.seat: each.plan for each in table.progress.plans}
    connection.execute(
        delete(auction_plans).where(
            auction_plans.c.table_id == table.id.value, auction_plans.c.seat.not_in(list(wanted))
        )
    )
    for seat, plan in wanted.items():
        occupant = table.chairs[seat - 1].occupant
        row = {
            "table_id": table.id.value,
            "seat": seat,
            "account_id": None if occupant is None else occupant.account_id,
            "kind": PASS_KIND if isinstance(plan, PassAhead) else LIMIT_KIND,
            "value": None if isinstance(plan, PassAhead) else plan.value,
            "mode": None if isinstance(plan, PassAhead) else plan.mode.value,
        }
        insertion = upsert(auction_plans).values(row)
        connection.execute(
            insertion.on_conflict_do_update(
                index_elements=[auction_plans.c.table_id, auction_plans.c.seat],
                set_={column: insertion.excluded[column] for column in ("account_id", "kind", "value", "mode")},
            )
        )
