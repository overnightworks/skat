"""Each finished game keeps one row in its table's list, numbered from one."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"

GAMES = ("karo", "herz", "pik", "kreuz", "grand", "null")
ANNOUNCEMENTS = ("none", "schneider", "schwarz")


def _one_of(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name)


def upgrade() -> None:
    op.create_table(
        "game_list",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("seat_1_account", sa.Text(), nullable=False),
        sa.Column("seat_2_account", sa.Text(), nullable=False),
        sa.Column("seat_3_account", sa.Text(), nullable=False),
        sa.Column("declarer_seat", sa.SmallInteger(), nullable=False),
        sa.Column("game", sa.Text(), nullable=False),
        sa.Column("hand", sa.Boolean(), nullable=False),
        sa.Column("ouvert", sa.Boolean(), nullable=False),
        sa.Column("announcement", sa.Text(), nullable=False),
        sa.Column("schneider", sa.Boolean(), nullable=False),
        sa.Column("schwarz", sa.Boolean(), nullable=False),
        sa.Column("matadors_mit", sa.Boolean()),
        sa.Column("matadors_count", sa.SmallInteger()),
        sa.Column("won", sa.Boolean(), nullable=False),
        sa.Column("bid", sa.SmallInteger(), nullable=False),
        sa.Column("game_value", sa.SmallInteger(), nullable=False),
        sa.Column("settled_value", sa.SmallInteger(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("declarer_points", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("ordinal >= 1", name="game_list_ordinal_counts_from_one"),
        sa.CheckConstraint("declarer_seat BETWEEN 1 AND 3", name="game_list_declarer_seat_is_a_seat"),
        _one_of("game", GAMES, "game_list_game_is_a_game"),
        _one_of("announcement", ANNOUNCEMENTS, "game_list_announcement_is_an_announcement"),
        sa.CheckConstraint(
            "num_nulls(matadors_mit, matadors_count) = CASE WHEN game = 'null' THEN 2 ELSE 0 END",
            name="game_list_matadors_only_outside_null",
        ),
        sa.CheckConstraint("matadors_count BETWEEN 1 AND 11", name="game_list_matadors_count_is_a_count"),
        sa.CheckConstraint("bid BETWEEN 18 AND 264", name="game_list_bid_is_a_bid"),
        sa.CheckConstraint("declarer_points BETWEEN 0 AND 120", name="game_list_declarer_points_are_card_points"),
    )
