"""A chair's mark names the revision of the next series' settings it was given on, and every write of a chair says so
itself, so no trigger has to clear that revision beside a release that does not name it.

The release before this one writes `ready_settings` with every chair it writes, and reads no trigger; this step drops
the trigger and its function that migration 0056 created.
"""

from alembic import op

revision = "0058"
down_revision = "0057"


def upgrade() -> None:
    op.execute("DROP TRIGGER chair_mark_taken_back_names_no_settings ON chairs")
    op.execute("DROP FUNCTION chair_mark_taken_back_names_no_settings()")
