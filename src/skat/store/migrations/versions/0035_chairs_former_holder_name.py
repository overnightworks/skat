"""A chair keeps the name of whoever last held it in the running hand and left it, so that every viewer is told whose
cards a sitter takes over. Every stored chair reads with no such name, an open chair of a running hand included.
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade() -> None:
    op.add_column("chairs", sa.Column("former_holder_name", sa.Text()))
