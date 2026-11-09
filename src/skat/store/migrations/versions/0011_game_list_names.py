"""Each game list row keeps the display names seated beside its accounts; old rows keep no names."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    for seat in (1, 2, 3):
        op.add_column("game_list", sa.Column(f"seat_{seat}_name", sa.Text()))
