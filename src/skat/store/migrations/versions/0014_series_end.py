"""A table keeps the standing proposal to end its series early and whether the series ended early; old tables
carry neither.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.add_column("tables", sa.Column("series_ended_early", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tables", sa.Column("series_end_proposer", sa.SmallInteger()))
    op.add_column("tables", sa.Column("series_end_accepter", sa.SmallInteger()))
    op.create_check_constraint(
        "tables_series_end_seats_are_seats",
        "tables",
        "series_end_proposer BETWEEN 1 AND 3 AND series_end_accepter BETWEEN 1 AND 3",
    )
    op.create_check_constraint(
        "tables_series_end_accepter_follows_a_proposer",
        "tables",
        "series_end_accepter IS NULL OR (series_end_proposer IS NOT NULL AND series_end_accepter <> series_end_proposer)",
    )
    op.create_check_constraint(
        "tables_series_end_needs_a_series",
        "tables",
        "series_length IS NOT NULL OR (series_end_proposer IS NULL AND NOT series_ended_early)",
    )
    op.create_check_constraint(
        "tables_series_ended_early_holds_no_proposal",
        "tables",
        "NOT series_ended_early OR series_end_proposer IS NULL",
    )
