"""A table has a style that the whole table shares: the column holds its token, and every table that exists is
classic.
"""

from alembic import op

revision = "0046"
down_revision = "0045"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tables ADD COLUMN style text NOT NULL DEFAULT 'klassik'"
        " CONSTRAINT tables_style_is_a_style CHECK (style IN ('klassik', 'strandbar'))"
    )
