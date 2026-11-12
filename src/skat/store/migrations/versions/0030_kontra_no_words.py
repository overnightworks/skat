"""A seat's answer that it says no word now is kept per hand: one row for each seat and word, gone with the hand. A
table stored before holds none, and an old hand's words are as they were.
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"

POSITIONS = ("forehand", "middlehand", "rearhand")
WORDS = ("kontra", "re", "supra", "hirsch")


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def upgrade() -> None:
    op.create_table(
        "kontra_no_words",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("position", sa.Text(), primary_key=True),
        sa.Column("word", sa.Text(), primary_key=True),
        sa.CheckConstraint(_is_one_of("position", POSITIONS), name="kontra_no_words_position_is_a_position"),
        sa.CheckConstraint(_is_one_of("word", WORDS), name="kontra_no_words_word_is_a_word"),
    )
