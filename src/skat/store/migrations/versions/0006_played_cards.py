"""Each card played keeps one row, in the order it was played."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"

POSITIONS = ("forehand", "middlehand", "rearhand")
SUITS = ("diamonds", "hearts", "spades", "clubs")
RANKS = ("seven", "eight", "nine", "ten", "jack", "queen", "king", "ace")


def _one_of(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name)


def upgrade() -> None:
    op.create_table(
        "played_cards",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("suit", sa.Text(), nullable=False),
        sa.Column("rank", sa.Text(), nullable=False),
        sa.UniqueConstraint("table_id", "suit", "rank", name="played_cards_each_card_once"),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 30", name="played_cards_ordinal_is_a_card_of_the_game"),
        _one_of("position", POSITIONS, "played_cards_position_is_a_position"),
        _one_of("suit", SUITS, "played_cards_suit_is_a_suit"),
        _one_of("rank", RANKS, "played_cards_rank_is_a_rank"),
    )
