"""A finished game is kept for good: a list row says which series of its table it belongs to and when its entry was
written, and the key holds the series number, so a next series counts its games from one again. A row stored before
belongs to its table's series and has no time.
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    op.add_column("game_list", sa.Column("series_number", sa.SmallInteger()))
    op.execute(
        "UPDATE game_list SET series_number = tables.series_number FROM tables WHERE tables.id = game_list.table_id"
    )
    op.alter_column("game_list", "series_number", nullable=False)
    op.add_column("game_list", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.drop_constraint("game_list_pkey", "game_list")
    op.create_primary_key("game_list_pkey", "game_list", ["table_id", "series_number", "ordinal"])
    op.create_check_constraint("game_list_series_number_counts_from_one", "game_list", "series_number >= 1")
