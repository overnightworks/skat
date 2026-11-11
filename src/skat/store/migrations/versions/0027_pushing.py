"""A table's Ramsch may have a stage of takes and pushes before its first card: the rule sits on the table row and on
a rule set, each seat's step in a log of its own, and a Ramsch's list entry says how often the skat was pushed on
unseen. A table stored before reads no pushing rule, and an old entry reads no push.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"

RULES = ("jacks-stay", "jacks-may-go", "no-doubling")
ACTIONS = ("take", "put-back", "push")
POSITIONS = ("forehand", "middlehand", "rearhand")
SUITS = ("diamonds", "hearts", "spades", "clubs")
RANKS = ("seven", "eight", "nine", "ten", "jack", "queen", "king", "ace")
STEPS_PER_STAGE = 6
PUSHES_PER_STAGE = 3


def _one_of(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=name)


def _upgrade_options() -> None:
    for table in ("tables", "rule_sets"):
        op.add_column(table, sa.Column("ramsch_pushing", sa.Text()))
        listed = ", ".join(f"'{rule}'" for rule in RULES)
        op.create_check_constraint(f"{table}_ramsch_pushing_is_a_pushing_rule", table, f"ramsch_pushing IN ({listed})")
        op.create_check_constraint(
            f"{table}_ramsch_pushing_needs_a_ramsch", table, "ramsch_pushing IS NULL OR ramsch_occasion IS NOT NULL"
        )


def _create_pushing_steps() -> None:
    op.create_table(
        "pushing_steps",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("first_suit", sa.Text()),
        sa.Column("first_rank", sa.Text()),
        sa.Column("second_suit", sa.Text()),
        sa.Column("second_rank", sa.Text()),
        sa.CheckConstraint(f"ordinal BETWEEN 1 AND {STEPS_PER_STAGE}", name="pushing_steps_ordinal_is_a_step"),
        _one_of("position", POSITIONS, "pushing_steps_position_is_a_position"),
        _one_of("action", ACTIONS, "pushing_steps_action_is_an_action"),
        _one_of("first_suit", SUITS, "pushing_steps_first_suit_is_a_suit"),
        _one_of("first_rank", RANKS, "pushing_steps_first_rank_is_a_rank"),
        _one_of("second_suit", SUITS, "pushing_steps_second_suit_is_a_suit"),
        _one_of("second_rank", RANKS, "pushing_steps_second_rank_is_a_rank"),
        sa.CheckConstraint(
            "num_nonnulls(first_suit, first_rank, second_suit, second_rank) "
            "= CASE WHEN action = 'put-back' THEN 4 ELSE 0 END",
            name="pushing_steps_cards_only_on_a_put_back",
        ),
        sa.CheckConstraint(
            "(first_suit, first_rank) <> (second_suit, second_rank)", name="pushing_steps_the_two_cards_differ"
        ),
    )


def _upgrade_game_list() -> None:
    op.add_column("game_list", sa.Column("pushes", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))
    op.create_check_constraint(
        "game_list_pushes_are_unseen_pushes", "game_list", f"pushes BETWEEN 0 AND {PUSHES_PER_STAGE}"
    )
    op.create_check_constraint("game_list_only_a_ramsch_is_pushed", "game_list", "kind = 'ramsch' OR pushes = 0")


def upgrade() -> None:
    _upgrade_options()
    _create_pushing_steps()
    _upgrade_game_list()
