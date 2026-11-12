"""An account's tables are found by an index on the chairs' account column instead of a scan of every chair; a free
chair is never looked up by account and stays out of it. The index adds no column and changes no row.
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"


def upgrade() -> None:
    op.create_index("chairs_by_account", "chairs", ["account_id"], postgresql_where=sa.text("account_id IS NOT NULL"))
