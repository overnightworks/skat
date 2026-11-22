"""A table keeps the trace of the request that moved it to its version, and the trace of each act of its latest hand.

All three columns are new and nullable. The release before writes none of them and reads none, so a version it moves
no longer equals `traceparent_version`, and an act it adds has no entry in `act_traceparents`: a reader takes the
version's trace only while the two versions agree, and an act's only where it has an entry.
"""

from alembic import op

revision = "0059"
down_revision = "0058"


def upgrade() -> None:
    op.execute("ALTER TABLE tables ADD COLUMN traceparent text")
    op.execute("ALTER TABLE tables ADD COLUMN traceparent_version integer")
    op.execute("ALTER TABLE tables ADD COLUMN act_traceparents jsonb")
