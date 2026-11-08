"""Receipts keep a refusal and who held the chair, so a retry returns its first outcome."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.add_column("receipts", sa.Column("refusal", sa.Text()))
    op.add_column("receipts", sa.Column("holder", sa.Text()))
