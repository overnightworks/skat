"""A series row exists from the save of its settings, before its first deal, and counts the saves; a chair that chose
„Neue Serie“ names the revision of the settings it chose on; a trigger clears that revision whenever a chair is written
not ready, so a mark the release before gives never inherits one."""

from alembic import op

revision = "0056"
down_revision = "0055"


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN settings_revision smallint NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE chairs ADD COLUMN ready_settings smallint")
    # The release before takes a mark back and gives it without naming the revision, so a revision a mark left behind
    # would stand for the next mark it gives, even one of another occupant: every write of a chair that is not ready
    # clears it.
    op.execute(
        """
        CREATE FUNCTION chair_mark_taken_back_names_no_settings() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT NEW.ready THEN
                NEW.ready_settings := NULL;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER chair_mark_taken_back_names_no_settings BEFORE UPDATE ON chairs "
        "FOR EACH ROW EXECUTE FUNCTION chair_mark_taken_back_names_no_settings()"
    )
