"""Each table keeps since when nobody has been at it, so a restart counts the empty wait on from there."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.add_column("tables", sa.Column("empty_since", sa.DateTime(timezone=True)))
