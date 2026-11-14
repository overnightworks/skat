"""A table and a rule set may play Ramsch rounds after Bock rounds, beside the third-pass Ramsch or instead of it. The
occasion check widens and a stored occasion keeps its token; a table also stores the Ramsch-round games still to come,
none for the tables that exist.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"

OCCASIONS = ("passed-in", "bock-rounds", "passed-in-and-bock-rounds")


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    for table in ("tables", "rule_sets"):
        name = f"{table}_ramsch_occasion_is_an_occasion"
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _is_one_of("ramsch_occasion", OCCASIONS))
    op.add_column("tables", sa.Column("ramsch_round_games", sa.SmallInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("tables_ramsch_round_games_are_not_negative", "tables", "ramsch_round_games >= 0")
