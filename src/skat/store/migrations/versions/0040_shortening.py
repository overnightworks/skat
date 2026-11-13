"""The declarer's shortening: the standing request keeps the level he demands and the opponent who said yes, a refusing
opponent's no is kept for the rest of the hand, and a game's list entry may say it was shortened. Only the ending check
widens.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"

_POSITIONS = ("forehand", "middlehand", "rearhand")
_ANNOUNCEMENTS = ("none", "schneider", "schwarz")
ENDING_CHECK = "game_list_ending_is_an_ending"


def _one_of(column: str, values: tuple[str, ...], name: str) -> None:
    op.create_check_constraint(name, "tables", f"{column} IN ({', '.join(f"'{value}'" for value in values)})")


def upgrade() -> None:
    op.add_column("tables", sa.Column("give_up_claim", sa.Text()))
    op.add_column("tables", sa.Column("give_up_agreed_by", sa.Text()))
    op.add_column("tables", sa.Column("shortening_refused_by", sa.Text()))
    _one_of("give_up_claim", _ANNOUNCEMENTS, "tables_give_up_claim_is_an_announcement")
    _one_of("give_up_agreed_by", _POSITIONS, "tables_give_up_agreer_is_a_position")
    _one_of("shortening_refused_by", _POSITIONS, "tables_shortening_refuser_is_a_position")
    op.create_check_constraint(
        "tables_give_up_claim_comes_with_an_ask", "tables", "give_up_claim IS NULL OR give_up_asked_by IS NOT NULL"
    )
    op.create_check_constraint(
        "tables_give_up_yes_comes_with_a_shortening_from_another_position",
        "tables",
        "give_up_agreed_by IS NULL OR (give_up_claim IS NOT NULL AND give_up_agreed_by <> give_up_asked_by)",
    )
    op.create_check_constraint(
        "tables_a_shortening_ends_with_its_first_no", "tables", "give_up_claim IS NULL OR give_up_declined_by IS NULL"
    )
    op.drop_constraint(ENDING_CHECK, "game_list", type_="check")
    op.create_check_constraint(
        ENDING_CHECK, "game_list", "ending IN ('played-out', 'given-up', 'thrown-down', 'shortened')"
    )
