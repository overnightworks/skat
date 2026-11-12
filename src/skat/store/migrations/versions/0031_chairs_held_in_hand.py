"""A chair keeps the accounts that held it in the running hand and left it, so that each may sit again only there
until the hand ends. Every stored chair reads with no such account, a running hand's included: the upgrade bars nobody.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"


def upgrade() -> None:
    op.add_column(
        "chairs", sa.Column("held_in_hand", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'"))
    )
    op.create_check_constraint(
        "chairs_held_in_hand_has_no_null", "chairs", "array_position(held_in_hand, NULL) IS NULL"
    )
