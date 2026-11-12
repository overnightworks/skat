"""A table's Ramsch stage may let a seat declare a Grand Hand instead of taking or pushing the skat: the choice sits on
the table row and on a rule set, next to the pushing rule, and the stage's log gains the step. A table stored before,
and every table that does not allow it, reads it off.
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"

RULES = ("allowed", "off")
ACTIONS = ("take", "put-back", "push", "grand-hand")
ACTION_CHECK = "pushing_steps_action_is_an_action"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _upgrade_options() -> None:
    for table in ("tables", "rule_sets"):
        op.add_column(table, sa.Column("ramsch_grand_hand", sa.Text()))
        op.create_check_constraint(
            f"{table}_ramsch_grand_hand_is_a_grand_hand_rule", table, f"ramsch_grand_hand IN ({_listed(RULES)})"
        )
        op.create_check_constraint(
            f"{table}_ramsch_grand_hand_needs_pushing",
            table,
            "ramsch_grand_hand IS NULL OR ramsch_pushing IS NOT NULL",
        )


def _widen_the_stage_log() -> None:
    op.drop_constraint(ACTION_CHECK, "pushing_steps", type_="check")
    op.create_check_constraint(ACTION_CHECK, "pushing_steps", f"action IN ({_listed(ACTIONS)})")


def upgrade() -> None:
    _upgrade_options()
    _widen_the_stage_log()
