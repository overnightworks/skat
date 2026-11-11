"""A dealt table keeps the time of its last deal or step of play, and a table the opener's name.

A live table dealt before this revision gets the migration's time, so its days count from the release; the opener's
name stays empty for every stored table, since chair 1 is no longer necessarily the opener.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade() -> None:
    op.add_column("tables", sa.Column("last_played_at", sa.DateTime(timezone=True)))
    op.add_column("tables", sa.Column("opener_name", sa.Text()))
    op.execute("UPDATE tables SET last_played_at = now() WHERE ended_at IS NULL AND dealer IS NOT NULL")
    op.create_check_constraint(
        "tables_a_dealt_table_has_its_last_played_time", "tables", "(dealer IS NULL) = (last_played_at IS NULL)"
    )
    op.create_check_constraint(
        "tables_an_ended_table_keeps_no_opener_name", "tables", "ended_at IS NULL OR opener_name IS NULL"
    )
    op.create_check_constraint("tables_opener_name_is_not_empty", "tables", "char_length(opener_name) >= 1")
