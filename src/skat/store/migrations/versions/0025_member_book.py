"""The invitation book: one row per agent and table with the table's epoch for it and its open invitation.

Expand only: the book is a new table and no stored table changes. An agent is a member of a table by holding a chair
there, so the book keeps no membership state.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade() -> None:
    op.create_table(
        "member_book",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("agent_account", sa.Text(), primary_key=True),
        sa.Column("epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invitation_id", sa.Text()),
        sa.Column("invitation_expires_at", sa.DateTime(timezone=True)),
        sa.Column("owner_account", sa.Text()),
        sa.Column("inviter_account", sa.Text()),
        sa.CheckConstraint(
            "num_nonnulls(invitation_id, invitation_expires_at, owner_account, inviter_account) IN (0, 4)",
            name="member_book_invitation_is_all_or_nothing",
        ),
        sa.CheckConstraint("epoch >= 0", name="member_book_epoch_is_not_negative"),
    )
