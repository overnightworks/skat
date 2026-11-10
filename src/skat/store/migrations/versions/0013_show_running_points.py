"""Each table keeps whether it shows the running points; a table stored before reads off."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.add_column("tables", sa.Column("show_running_points", sa.Boolean(), nullable=False, server_default=sa.false()))
