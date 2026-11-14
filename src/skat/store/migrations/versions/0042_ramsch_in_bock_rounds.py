"""A table and a rule set may play Ramsch in Bock rounds, beside the third-pass Ramsch or instead of it. Only the
occasion check widens; a stored occasion keeps its token.
"""

from alembic import op

revision = "0042"
down_revision = "0041"

OCCASIONS = ("passed-in", "bock-rounds", "passed-in-and-bock-rounds")


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    for table in ("tables", "rule_sets"):
        name = f"{table}_ramsch_occasion_is_an_occasion"
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _is_one_of("ramsch_occasion", OCCASIONS))
