"""A table keeps the number of its series; a table stored before reads its first."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    op.add_column("tables", sa.Column("series_number", sa.SmallInteger(), nullable=False, server_default="1"))
    op.create_check_constraint("tables_series_number_is_a_number", "tables", "series_number >= 1")
    op.create_check_constraint(
        "tables_series_numbers_only_with_a_series", "tables", "series_length IS NOT NULL OR series_number = 1"
    )
