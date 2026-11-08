"""Each step of a running auction keeps one row, in the order it was taken."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"

POSITIONS = ("forehand", "middlehand", "rearhand")
ACTIONS = ("bid", "hold", "pass", "play")


def _one_of(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name)


def upgrade() -> None:
    op.create_table(
        "auction_actions",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("value", sa.SmallInteger()),
        _one_of("position", POSITIONS, "auction_actions_position_is_a_position"),
        _one_of("action", ACTIONS, "auction_actions_action_is_an_action"),
        sa.CheckConstraint("(action = 'bid') = (value IS NOT NULL)", name="auction_actions_value_only_on_a_bid"),
        sa.CheckConstraint("value BETWEEN 18 AND 264", name="auction_actions_value_is_a_bid"),
    )
