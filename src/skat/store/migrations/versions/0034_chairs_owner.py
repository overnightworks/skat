"""A chair keeps the owner of the agent that sits in it, so that its owner may send it away. Every stored chair reads
with no owner, an agent's included.
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"


def upgrade() -> None:
    op.add_column("chairs", sa.Column("owner_account", sa.Text()))
    op.create_check_constraint(
        "chairs_owner_only_of_an_agent",
        "chairs",
        "owner_account IS NULL OR occupant_kind IS NOT DISTINCT FROM 'agent'",
    )
