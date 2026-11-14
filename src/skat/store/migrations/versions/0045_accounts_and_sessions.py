"""Accounts and sessions: the sign-in's accounts by issuer subject and their sessions, the session id stored only as its
hash.

Expand only: two new tables and no stored table changes. A session ends with its account; no other table references an
account, because the domain holds issuer subjects, some of which never signed in.
"""

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.CheckConstraint("kind IN ('person', 'agent')", name="accounts_kind_is_a_kind"),
    )
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.Text(), primary_key=True),
        sa.Column("account_id", sa.Text(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("id_token", sa.Text()),
        sa.Column("account_language", sa.Text()),
    )
    op.create_index("sessions_account_created_at", "sessions", ["account_id", "created_at"])
    op.create_index("sessions_expires_at", "sessions", ["expires_at"])
