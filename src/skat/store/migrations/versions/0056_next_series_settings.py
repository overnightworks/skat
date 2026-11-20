"""A series row exists from the save of its settings, before its first deal, and counts the saves; a chair that chose
„Neue Serie“ names the revision of the settings it chose on."""

from alembic import op

revision = "0056"
down_revision = "0055"


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN settings_revision smallint NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE chairs ADD COLUMN ready_settings smallint")
