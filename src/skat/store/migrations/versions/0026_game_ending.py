"""A declared game's list entry keeps how the game ended and, after a give-up or a throw-down, the seat that did it.

The engine's ending cannot tell a give-up from a game its points decided, so the table records it. An entry stored
before reads `played-out` with no seat, which is what it cannot be told from.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"

ENDINGS = ("played-out", "given-up", "thrown-down")
SEATS = 3


def upgrade() -> None:
    op.add_column("game_list", sa.Column("ending", sa.Text(), nullable=False, server_default="played-out"))
    op.add_column("game_list", sa.Column("ended_by_seat", sa.SmallInteger()))
    listed = ", ".join(f"'{ending}'" for ending in ENDINGS)
    op.create_check_constraint("game_list_ending_is_an_ending", "game_list", f"ending IN ({listed})")
    op.create_check_constraint("game_list_ended_by_seat_is_a_seat", "game_list", f"ended_by_seat BETWEEN 1 AND {SEATS}")
    op.create_check_constraint(
        "game_list_a_seat_ends_exactly_an_unplayed_game",
        "game_list",
        "(ending = 'played-out') = (ended_by_seat IS NULL)",
    )
    op.create_check_constraint(
        "game_list_a_ramsch_is_played_out", "game_list", "kind <> 'ramsch' OR ending = 'played-out'"
    )
