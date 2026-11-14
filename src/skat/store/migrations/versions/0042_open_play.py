"""An opponent's wrong open play waits for the declarer's answer as a standing request, and a game's list entry may say
it ended by an open play. Only the ending check widens.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"

ENDING_CHECK = "game_list_ending_is_an_ending"


def upgrade() -> None:
    op.add_column("tables", sa.Column("give_up_open", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint(
        "tables_an_open_play_is_asked_of_the_declarer_alone",
        "tables",
        "NOT give_up_open OR (give_up_asked_by IS NOT NULL AND give_up_claim IS NULL AND give_up_declined_by IS NULL"
        " AND give_up_agreed_by IS NULL)",
    )
    op.drop_constraint(ENDING_CHECK, "game_list", type_="check")
    op.create_check_constraint(
        ENDING_CHECK,
        "game_list",
        "ending IN ('played-out', 'given-up', 'thrown-down', 'shortened', 'played-open')",
    )
