"""A dealt table that nobody plays at for the paused-table days ends by itself: the end stores the days in force, so a
later change of the setting never changes what an old link says. Only the reason check widens.
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"

REASON_CHECK = "tables_end_reason_is_a_reason"


def upgrade() -> None:
    op.add_column("tables", sa.Column("unplayed_days", sa.Integer()))
    op.create_check_constraint(
        "tables_unplayed_days_only_for_an_unplayed_end",
        "tables",
        "(unplayed_days IS NOT NULL) = (end_reason IS NOT DISTINCT FROM 'unplayed')",
    )
    op.create_check_constraint("tables_unplayed_days_are_positive", "tables", "unplayed_days > 0")
    op.drop_constraint(REASON_CHECK, "tables", type_="check")
    op.create_check_constraint(REASON_CHECK, "tables", "end_reason IN ('empty', 'unplayed')")
