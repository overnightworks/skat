"""A closed table keeps its closer's name only for the days its link names why it ended: the name column may then be
empty on a closed end, and stays empty on every other row.
"""

from alembic import op

revision = "0044"
down_revision = "0043"

NAME_CHECK = "tables_closed_by_name_only_for_a_closed_end"


def upgrade() -> None:
    op.drop_constraint(NAME_CHECK, "tables", type_="check")
    op.create_check_constraint(
        NAME_CHECK, "tables", "closed_by_name IS NULL OR end_reason IS NOT DISTINCT FROM 'closed'"
    )
