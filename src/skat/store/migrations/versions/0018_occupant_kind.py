"""Each chair keeps whether a person or an agent sits in it; the chairs occupied before are people's."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade() -> None:
    op.add_column("chairs", sa.Column("occupant_kind", sa.Text()))
    op.execute("UPDATE chairs SET occupant_kind = 'person' WHERE account_id IS NOT NULL")
    op.create_check_constraint(
        "chairs_kind_only_when_occupied", "chairs", "(account_id IS NULL) = (occupant_kind IS NULL)"
    )
    op.create_check_constraint("chairs_occupant_kind_is_a_kind", "chairs", "occupant_kind IN ('person', 'agent')")
