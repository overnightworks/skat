"""A table may play Ramsch: its four options sit on the table row and on a rule set, and the game list holds Ramsch
entries beside declared ones. A row says its kind, a table stored before reads no Ramsch and an old row reads
`declared`. A declared game's columns may be empty now, one check per kind says which columns each kind fills.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"

OPTIONS = {
    "ramsch_occasion": ("passed-in",),
    "ramsch_scoring": ("points", "points-by-ten", "skat-to-loser"),
    "ramsch_jungfrau": ("doubles-loser", "off"),
    "ramsch_durchmarsch": ("wins-120", "wins-120-flat", "off"),
}
OPTION_CHECK_NAMES = {
    "ramsch_occasion": "an_occasion",
    "ramsch_scoring": "a_scoring",
    "ramsch_jungfrau": "a_jungfrau_rule",
    "ramsch_durchmarsch": "a_durchmarsch_rule",
}
DECLARED_COLUMNS = (
    "declarer_seat",
    "game",
    "hand",
    "ouvert",
    "announcement",
    "schneider",
    "schwarz",
    "won",
    "bid",
    "game_value",
    "settled_value",
    "score",
    "declarer_points",
)
RAMSCH_COLUMNS = (
    "seat_1_points",
    "seat_2_points",
    "seat_3_points",
    "seat_1_score",
    "seat_2_score",
    "seat_3_score",
    "jungfrau",
)
KINDS = ("declared", "ramsch")
ALL_POINTS = 120


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def _fills_its_columns() -> str:
    declared = ", ".join(DECLARED_COLUMNS)
    ramsch = ", ".join(RAMSCH_COLUMNS)
    return (
        f"CASE kind WHEN 'declared' THEN num_nonnulls({declared}) = {len(DECLARED_COLUMNS)}"
        f" AND num_nonnulls({ramsch}, durchmarsch_seat) = 0"
        f" WHEN 'ramsch' THEN num_nonnulls({declared}) = 0 AND num_nonnulls({ramsch}) = {len(RAMSCH_COLUMNS)}"
        " AND num_nonnulls(matadors_mit, matadors_count, kontra_word) = 0 END"
    )


def _upgrade_options() -> None:
    for table in ("tables", "rule_sets"):
        for column in OPTIONS:
            op.add_column(table, sa.Column(column, sa.Text()))
        columns = ", ".join(OPTIONS)
        op.create_check_constraint(
            f"{table}_ramsch_is_all_or_nothing", table, f"num_nonnulls({columns}) IN (0, {len(OPTIONS)})"
        )
        for column, values in OPTIONS.items():
            op.create_check_constraint(
                f"{table}_{column}_is_{OPTION_CHECK_NAMES[column]}", table, _is_one_of(column, values)
            )


def _upgrade_game_list() -> None:
    op.add_column("game_list", sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'declared'")))
    for seat in (1, 2, 3):
        op.add_column("game_list", sa.Column(f"seat_{seat}_points", sa.SmallInteger()))
        op.add_column("game_list", sa.Column(f"seat_{seat}_score", sa.Integer()))
    op.add_column("game_list", sa.Column("durchmarsch_seat", sa.SmallInteger()))
    op.add_column("game_list", sa.Column("jungfrau", sa.Boolean()))
    for column in DECLARED_COLUMNS:
        op.alter_column("game_list", column, nullable=True)
    op.drop_constraint("game_list_matadors_only_outside_null", "game_list")
    op.create_check_constraint(
        "game_list_matadors_only_outside_null",
        "game_list",
        "num_nulls(matadors_mit, matadors_count) = CASE WHEN kind = 'ramsch' OR game = 'null' THEN 2 ELSE 0 END",
    )
    op.create_check_constraint("game_list_kind_is_a_kind", "game_list", _is_one_of("kind", KINDS))
    op.create_check_constraint("game_list_kind_fills_its_columns", "game_list", _fills_its_columns())
    points = " AND ".join(f"seat_{seat}_points BETWEEN 0 AND {ALL_POINTS}" for seat in (1, 2, 3))
    op.create_check_constraint("game_list_ramsch_points_are_card_points", "game_list", points)
    op.create_check_constraint("game_list_durchmarsch_seat_is_a_seat", "game_list", "durchmarsch_seat BETWEEN 1 AND 3")


def upgrade() -> None:
    _upgrade_options()
    _upgrade_game_list()
