"""A finished game keeps its cards, one row per card and pile: the hands as the game started, the skat as it lay, the
cards put away and the tricks with the seat and place of each card. A game finished before has no rows.
"""

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"

SUITS = ("diamonds", "hearts", "spades", "clubs")
RANKS = ("seven", "eight", "nine", "ten", "jack", "queen", "king", "ace")
PILES = ("hand", "skat", "put-away", "trick")
GAME = ("table_id", "series_number", "ordinal")


def upgrade() -> None:
    op.create_table(
        "game_cards",
        sa.Column("table_id", sa.Text(), nullable=False),
        sa.Column("series_number", sa.SmallInteger(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("pile", sa.Text(), nullable=False),
        sa.Column("seat", sa.SmallInteger()),
        sa.Column("trick", sa.SmallInteger()),
        sa.Column("place", sa.SmallInteger()),
        sa.Column("suit", sa.Text(), nullable=False),
        sa.Column("rank", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(list(GAME), [f"game_list.{column}" for column in GAME]),
        sa.CheckConstraint(sa.column("pile").in_(PILES), name="game_cards_pile_is_a_pile"),
        sa.CheckConstraint("seat BETWEEN 1 AND 3", name="game_cards_seat_is_a_seat"),
        sa.CheckConstraint("trick BETWEEN 1 AND 10", name="game_cards_trick_is_a_trick_of_the_game"),
        sa.CheckConstraint("place BETWEEN 1 AND 3", name="game_cards_place_is_a_place_in_a_trick"),
        sa.CheckConstraint(sa.column("suit").in_(SUITS), name="game_cards_suit_is_a_suit"),
        sa.CheckConstraint(sa.column("rank").in_(RANKS), name="game_cards_rank_is_a_rank"),
        sa.CheckConstraint(
            "CASE pile"
            " WHEN 'hand' THEN seat IS NOT NULL AND trick IS NULL AND place IS NULL"
            " WHEN 'skat' THEN seat IS NULL AND trick IS NULL AND place IS NULL"
            " WHEN 'put-away' THEN seat IS NOT NULL AND trick IS NULL AND place IS NULL"
            " WHEN 'trick' THEN seat IS NOT NULL AND trick IS NOT NULL AND place IS NOT NULL END",
            name="game_cards_a_pile_names_what_it_is_in",
        ),
    )
    op.create_index(
        "game_cards_each_card_dealt_once",
        "game_cards",
        [*GAME, "suit", "rank"],
        unique=True,
        postgresql_where=sa.text("pile IN ('hand', 'skat')"),
    )
    op.create_index(
        "game_cards_each_card_played_once",
        "game_cards",
        [*GAME, "suit", "rank"],
        unique=True,
        postgresql_where=sa.text("pile = 'trick'"),
    )
    op.create_index(
        "game_cards_each_place_taken_once",
        "game_cards",
        [*GAME, "trick", "place"],
        unique=True,
        postgresql_where=sa.text("pile = 'trick'"),
    )
    op.create_index(
        "game_cards_a_seat_puts_a_card_away_once",
        "game_cards",
        [*GAME, "seat", "suit", "rank"],
        unique=True,
        postgresql_where=sa.text("pile = 'put-away'"),
    )
