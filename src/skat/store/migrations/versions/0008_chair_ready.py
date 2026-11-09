"""Each chair keeps whether its occupant tapped „Weiter“ after the pending result; a free chair is never ready."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.add_column("chairs", sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint("chairs_ready_only_when_occupied", "chairs", "account_id IS NOT NULL OR NOT ready")
