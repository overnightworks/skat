"""A table keeps its dealer, and a dealt hand keeps one row per card."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"

SUITS = ("diamonds", "hearts", "spades", "clubs")
RANKS = ("seven", "eight", "nine", "ten", "jack", "queen", "king", "ace")
HOLDERS = ("forehand", "middlehand", "rearhand", "skat")


def _one_of(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name)


def upgrade() -> None:
    op.add_column("tables", sa.Column("dealer", sa.SmallInteger()))
    op.create_check_constraint("tables_dealer_is_a_seat", "tables", "dealer BETWEEN 1 AND 3")
    op.create_table(
        "hand_cards",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("suit", sa.Text(), primary_key=True),
        sa.Column("rank", sa.Text(), primary_key=True),
        sa.Column("holder", sa.Text(), nullable=False),
        _one_of("suit", SUITS, "hand_cards_suit_is_a_suit"),
        _one_of("rank", RANKS, "hand_cards_rank_is_a_rank"),
        _one_of("holder", HOLDERS, "hand_cards_holder_is_a_holder"),
    )
