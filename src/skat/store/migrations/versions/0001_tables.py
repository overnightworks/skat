"""Tables, their chairs and the command receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "tables",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "chairs",
        sa.Column("table_id", sa.Text(), sa.ForeignKey("tables.id"), primary_key=True),
        sa.Column("seat", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Text()),
        sa.Column("display_name", sa.Text()),
    )
    op.create_table(
        "receipts",
        sa.Column("account_id", sa.Text(), primary_key=True),
        sa.Column("command_id", sa.Text(), primary_key=True),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("table_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["table_id"], ["tables.id"]),
    )
