"""The seated players may vote to abort a hand while one of its chairs is open: the table keeps the seats that said yes
and whether its last hand ended by that vote. Every stored table reads with no proposal and no aborted hand.
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"


def upgrade() -> None:
    op.add_column(
        "tables",
        sa.Column("abort_yes_seats", sa.ARRAY(sa.SmallInteger()), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("tables", sa.Column("hand_aborted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint(
        "tables_abort_yes_are_seats",
        "tables",
        "abort_yes_seats <@ ARRAY[1, 2, 3]::smallint[] AND array_position(abort_yes_seats, NULL) IS NULL",
    )
    op.create_check_constraint(
        "tables_an_aborted_hand_holds_no_proposal", "tables", "NOT hand_aborted OR cardinality(abort_yes_seats) = 0"
    )
