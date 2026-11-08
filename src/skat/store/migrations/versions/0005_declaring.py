"""Each step the declarer takes keeps one row, in the order it was taken."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"

ACTIONS = ("take", "put-back", "declare")
SUITS = ("diamonds", "hearts", "spades", "clubs")
RANKS = ("seven", "eight", "nine", "ten", "jack", "queen", "king", "ace")
GAMES = ("karo", "herz", "pik", "kreuz", "grand", "null")
ANNOUNCEMENTS = ("none", "schneider", "schwarz")


def _one_of(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name)


def upgrade() -> None:
    op.create_table(
        "declaring_steps",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("first_suit", sa.Text()),
        sa.Column("first_rank", sa.Text()),
        sa.Column("second_suit", sa.Text()),
        sa.Column("second_rank", sa.Text()),
        sa.Column("game", sa.Text()),
        sa.Column("hand", sa.Boolean()),
        sa.Column("ouvert", sa.Boolean()),
        sa.Column("announcement", sa.Text()),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 3", name="declaring_steps_ordinal_is_a_step"),
        _one_of("action", ACTIONS, "declaring_steps_action_is_an_action"),
        _one_of("first_suit", SUITS, "declaring_steps_first_suit_is_a_suit"),
        _one_of("first_rank", RANKS, "declaring_steps_first_rank_is_a_rank"),
        _one_of("second_suit", SUITS, "declaring_steps_second_suit_is_a_suit"),
        _one_of("second_rank", RANKS, "declaring_steps_second_rank_is_a_rank"),
        _one_of("game", GAMES, "declaring_steps_game_is_a_game"),
        _one_of("announcement", ANNOUNCEMENTS, "declaring_steps_announcement_is_an_announcement"),
        sa.CheckConstraint(
            "num_nonnulls(first_suit, first_rank, second_suit, second_rank) "
            "= CASE WHEN action = 'put-back' THEN 4 ELSE 0 END",
            name="declaring_steps_cards_only_on_a_put_back",
        ),
        sa.CheckConstraint(
            "(first_suit, first_rank) <> (second_suit, second_rank)",
            name="declaring_steps_the_two_cards_differ",
        ),
        sa.CheckConstraint(
            "num_nonnulls(game, hand, ouvert, announcement) = CASE WHEN action = 'declare' THEN 4 ELSE 0 END",
            name="declaring_steps_game_only_on_a_declare",
        ),
    )
