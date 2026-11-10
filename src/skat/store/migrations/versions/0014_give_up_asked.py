"""Each table keeps the give-up its declarer asked for and the opponent who said no, until a card or the hand's end."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"

_POSITIONS = ("forehand", "middlehand", "rearhand")


def _one_of(column: str, name: str) -> None:
    op.create_check_constraint(name, "tables", f"{column} IN ({', '.join(f"'{position}'" for position in _POSITIONS)})")


def upgrade() -> None:
    op.add_column("tables", sa.Column("give_up_asked_by", sa.Text()))
    op.add_column("tables", sa.Column("give_up_declined_by", sa.Text()))
    _one_of("give_up_asked_by", "tables_give_up_asker_is_a_position")
    _one_of("give_up_declined_by", "tables_give_up_decliner_is_a_position")
    op.create_check_constraint(
        "tables_give_up_no_comes_with_an_ask",
        "tables",
        "give_up_declined_by IS NULL OR give_up_asked_by IS NOT NULL",
    )
    op.create_check_constraint(
        "tables_give_up_no_comes_from_another_position", "tables", "give_up_declined_by <> give_up_asked_by"
    )
