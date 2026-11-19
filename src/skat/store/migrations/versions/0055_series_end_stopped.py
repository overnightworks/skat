"""A table ends at its series' end by „Aufhören“ or by a seat silent for the minute: the end reason `stopped` joins
the others, and a series that is over stores the instant of its first „Neue Serie“, from which a silent seat counts
as no. The release before never writes the instant, so a trigger clears the one a deal or a proposal of the release
before left behind.
"""

from alembic import op

revision = "0055"
down_revision = "0054"

REASON_CHECK = "tables_end_reason_is_a_reason"


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN new_series_asked_at timestamptz")
    op.drop_constraint(REASON_CHECK, "tables", type_="check")
    op.create_check_constraint(REASON_CHECK, "tables", "end_reason IN ('empty', 'unplayed', 'closed', 'stopped')")
    op.execute(
        """
        CREATE FUNCTION series_new_series_ask_ends_with_the_series_end() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.deals IS DISTINCT FROM OLD.deals OR NEW.end_proposer IS NOT NULL THEN
                NEW.new_series_asked_at := NULL;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER series_new_series_ask_ends_with_the_series_end BEFORE UPDATE ON series "
        "FOR EACH ROW EXECUTE FUNCTION series_new_series_ask_ends_with_the_series_end()"
    )
