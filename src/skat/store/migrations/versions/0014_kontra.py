"""A table may play Kontra and Re: its three options sit on the table row, the words of a running hand keep one row
each, and a game list row keeps the last word; old tables play without and old rows name no word.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"

SAYERS = ("any-opponent", "bidders-only")
REACHES = ("kontra-re", "kontra-re-standings", "up-to-hirsch")
DEADLINES = ("own-card", "first-card")
POSITIONS = ("forehand", "middlehand", "rearhand")
WORDS = ("kontra", "re", "supra", "hirsch")


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def upgrade() -> None:
    for column in ("kontra_sayer", "kontra_reach", "kontra_deadline"):
        op.add_column("tables", sa.Column(column, sa.Text()))
    op.create_check_constraint(
        "tables_kontra_is_all_or_nothing",
        "tables",
        "num_nonnulls(kontra_sayer, kontra_reach, kontra_deadline) IN (0, 3)",
    )
    op.create_check_constraint("tables_kontra_sayer_is_a_sayer", "tables", _is_one_of("kontra_sayer", SAYERS))
    op.create_check_constraint("tables_kontra_reach_is_a_reach", "tables", _is_one_of("kontra_reach", REACHES))
    op.create_check_constraint(
        "tables_kontra_deadline_is_a_deadline", "tables", _is_one_of("kontra_deadline", DEADLINES)
    )
    op.create_table(
        "kontra_words",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("cards_before", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 4", name="kontra_words_ordinal_is_a_word_of_the_hand"),
        sa.CheckConstraint("cards_before BETWEEN 0 AND 29", name="kontra_words_cards_before_are_cards_of_the_game"),
        sa.CheckConstraint(_is_one_of("position", POSITIONS), name="kontra_words_position_is_a_position"),
        sa.CheckConstraint(_is_one_of("word", WORDS), name="kontra_words_word_is_a_word"),
    )
    op.add_column("game_list", sa.Column("kontra_word", sa.Text()))
    op.create_check_constraint("game_list_kontra_word_is_a_word", "game_list", _is_one_of("kontra_word", WORDS))
