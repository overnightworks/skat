"""A chair hold is a deadline stored beside its table, so any pod frees the chair once it is due. The rows go with a
forgotten table: the previous release deletes tables without knowing this one.
"""

from alembic import op

revision = "0051"
down_revision = "0050"


def upgrade() -> None:
    op.execute(
        "CREATE TABLE chair_holds ("
        " table_id text NOT NULL REFERENCES tables (id) ON DELETE CASCADE,"
        " account_id text NOT NULL,"
        " due_at timestamptz NOT NULL,"
        " PRIMARY KEY (table_id, account_id))"
    )
    op.execute("CREATE INDEX chair_holds_by_due ON chair_holds (due_at)")
