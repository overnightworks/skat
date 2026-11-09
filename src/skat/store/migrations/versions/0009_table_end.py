"""A table keeps when and why it ended; the end itself deletes everything else of it but the row."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.add_column("tables", sa.Column("ended_at", sa.DateTime(timezone=True)))
    op.add_column("tables", sa.Column("end_reason", sa.Text()))
    op.add_column("tables", sa.Column("empty_seconds", sa.Integer()))
    op.create_check_constraint(
        "tables_end_time_comes_with_its_reason", "tables", "(ended_at IS NULL) = (end_reason IS NULL)"
    )
    op.create_check_constraint(
        "tables_empty_seconds_only_for_an_empty_end",
        "tables",
        "(empty_seconds IS NOT NULL) = (end_reason IS NOT DISTINCT FROM 'empty')",
    )
    op.create_check_constraint("tables_empty_seconds_are_positive", "tables", "empty_seconds > 0")
    op.create_check_constraint("tables_end_reason_is_a_reason", "tables", "end_reason IN ('empty')")
