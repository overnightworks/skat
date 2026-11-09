"""A table may carry a series: its length in games and the deals made so far; old tables carry none."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.add_column("tables", sa.Column("series_length", sa.SmallInteger()))
    op.add_column("tables", sa.Column("series_deals", sa.SmallInteger()))
    op.create_check_constraint(
        "tables_series_is_both_or_neither", "tables", "(series_length IS NULL) = (series_deals IS NULL)"
    )
    op.create_check_constraint(
        "tables_series_length_is_a_length",
        "tables",
        "series_length BETWEEN 3 AND 99 AND series_length % 3 = 0",
    )
    op.create_check_constraint(
        "tables_series_deals_are_within_the_length", "tables", "series_deals BETWEEN 0 AND series_length"
    )
