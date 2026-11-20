"""A series row exists from the save of its settings, before its first deal, and counts the saves."""

from alembic import op

revision = "0056"
down_revision = "0055"


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN settings_revision smallint NOT NULL DEFAULT 0")
