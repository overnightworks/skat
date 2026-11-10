"""A table may deal Bock rounds: its triggers and overlap sit on the table row beside the pending Bock games, and a
game list row keeps the factor its score was multiplied by; old tables play without Bock and old rows have factor 1.
The score widens because a Bock factor and a Kontra word multiply a lost game's score beyond 32767.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"

TRIGGERS = (
    "sixty-sixty",
    "won-grand-hand",
    "lost-after-kontra",
    "re",
    "passed-in",
    "schneider",
    "schwarz",
    "total-ending-in-00",
)
OVERLAPS = ("append", "multiply", "ignore")
GAMES_IN_A_ROUND = 3


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def upgrade() -> None:
    op.add_column("tables", sa.Column("bock_triggers", sa.ARRAY(sa.Text())))
    op.add_column("tables", sa.Column("bock_overlap", sa.Text()))
    op.add_column(
        "tables", sa.Column("bock_rounds", sa.ARRAY(sa.SmallInteger()), nullable=False, server_default=sa.text("'{}'"))
    )
    op.create_check_constraint(
        "tables_bock_is_all_or_nothing", "tables", "(bock_triggers IS NULL) = (bock_overlap IS NULL)"
    )
    listed_triggers = ", ".join(f"'{trigger}'" for trigger in TRIGGERS)
    op.create_check_constraint(
        "tables_bock_triggers_are_triggers",
        "tables",
        f"cardinality(bock_triggers) >= 1 AND bock_triggers <@ ARRAY[{listed_triggers}]::text[]",
    )
    op.create_check_constraint("tables_bock_overlap_is_an_overlap", "tables", _is_one_of("bock_overlap", OVERLAPS))
    listed_rounds = ", ".join(str(games) for games in range(1, GAMES_IN_A_ROUND + 1))
    op.create_check_constraint(
        "tables_bock_rounds_are_rounds_with_games_left",
        "tables",
        f"bock_rounds <@ ARRAY[{listed_rounds}]::smallint[] AND array_position(bock_rounds, NULL) IS NULL",
    )
    op.create_check_constraint(
        "tables_bock_rounds_only_with_bock", "tables", "bock_triggers IS NOT NULL OR cardinality(bock_rounds) = 0"
    )
    op.add_column("game_list", sa.Column("bock_factor", sa.SmallInteger(), nullable=False, server_default=sa.text("1")))
    op.create_check_constraint(
        "game_list_bock_factor_is_a_power_of_two",
        "game_list",
        "bock_factor > 0 AND bock_factor & (bock_factor - 1) = 0",
    )
    op.alter_column("game_list", "score", type_=sa.Integer(), existing_nullable=False)
