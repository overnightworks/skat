"""The opener closes a table for everyone: the end stores the closer's display name beside the reason, which the
closed table's link names. Only the reason check widens.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0036"

REASON_CHECK = "tables_end_reason_is_a_reason"


def upgrade() -> None:
    op.add_column("tables", sa.Column("closed_by_name", sa.Text()))
    op.create_check_constraint(
        "tables_closed_by_name_only_for_a_closed_end",
        "tables",
        "(closed_by_name IS NOT NULL) = (end_reason IS NOT DISTINCT FROM 'closed')",
    )
    op.create_check_constraint("tables_closed_by_name_is_not_empty", "tables", "char_length(closed_by_name) >= 1")
    op.drop_constraint(REASON_CHECK, "tables", type_="check")
    op.create_check_constraint(REASON_CHECK, "tables", "end_reason IN ('empty', 'unplayed', 'closed')")
