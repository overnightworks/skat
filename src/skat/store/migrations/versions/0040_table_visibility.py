"""A table is opened open or private: the column holds who the lobby lists it to, and every table that exists is
open.
"""

from alembic import op

revision = "0040"
down_revision = "0039"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tables ADD COLUMN visibility text NOT NULL DEFAULT 'open'"
        " CONSTRAINT tables_visibility_is_a_visibility CHECK (visibility IN ('open', 'private'))"
    )
