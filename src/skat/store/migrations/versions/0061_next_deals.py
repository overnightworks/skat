"""A next-deal pause is a deadline stored beside its table, so any pod deals once it is due. The rows go with a
forgotten table: the previous release deletes tables without knowing this one. That release keeps dealing from its own
timers and never writes a row, so a deal it made before a row fell due leaves the row to the sweep, which deletes it
without dealing.
"""

from alembic import op

revision = "0061"
down_revision = "0060"


def upgrade() -> None:
    op.execute(
        "CREATE TABLE next_deals ("
        " table_id text PRIMARY KEY REFERENCES tables (id) ON DELETE CASCADE,"
        " due_at timestamptz NOT NULL)"
    )
    op.execute("CREATE INDEX next_deals_by_due ON next_deals (due_at)")
