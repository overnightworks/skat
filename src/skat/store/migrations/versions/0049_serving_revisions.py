"""The database lists the revisions whose code may run on it, so that a process of an older release keeps serving
while a newer release has migrated the database by steps that only expand. `skat migrate` fills the table in the
transaction of its steps, once the table exists.
"""

from alembic import op

revision = "0049"
down_revision = "0048"


def upgrade() -> None:
    op.execute("CREATE TABLE serving_revisions (revision text PRIMARY KEY)")
