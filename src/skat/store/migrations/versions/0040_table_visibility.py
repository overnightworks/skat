"""A table is opened open or private: the column holds who the lobby lists it to, and every table that exists is
open.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"


def upgrade() -> None:
    op.add_column("tables", sa.Column("visibility", sa.Text(), nullable=False, server_default="open"))
    op.create_check_constraint("tables_visibility_is_a_visibility", "tables", "visibility IN ('open', 'private')")
