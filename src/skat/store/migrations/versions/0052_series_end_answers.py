"""Every seat answers a proposal to end the series, and the proposal's instant is stored: the seats that said yes, the
instant the proposal was made, from which a silent seat counts as no, and the seats whose no ended the last proposal.
The proposer stays in `end_proposer` and the one other seat that said yes in `end_accepter`, as the release before wrote
them, which serves beside this one; its writes leave the new columns as they were, so a trigger reads the proposal it
wrote into them. A proposal standing at the migration gets its yes list and starts its minute now.
"""

from alembic import op

revision = "0052"
down_revision = "0051"


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN end_agreed smallint[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE series ADD COLUMN end_asked_at timestamptz")
    op.execute("ALTER TABLE series ADD COLUMN end_refused_by smallint[] NOT NULL DEFAULT '{}'")
    op.execute(
        "UPDATE series SET end_asked_at = now(), end_agreed = array_remove(ARRAY[end_proposer, end_accepter], NULL) "
        "WHERE end_proposer IS NOT NULL"
    )
    # A write that moves the proposer or the accepter and leaves the yes list and the instant as they were is the
    # release before's: its proposal gets the yes list of its seats, a minute of its own if it is new, and none at all
    # if it ended.
    op.execute(
        """
        CREATE FUNCTION series_end_written_by_the_release_before() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.end_proposer, NEW.end_accepter) IS DISTINCT FROM (OLD.end_proposer, OLD.end_accepter)
               AND NEW.end_agreed = OLD.end_agreed
               AND NEW.end_asked_at IS NOT DISTINCT FROM OLD.end_asked_at THEN
                NEW.end_agreed := array_remove(ARRAY[NEW.end_proposer, NEW.end_accepter], NULL);
                NEW.end_asked_at := CASE
                    WHEN NEW.end_proposer IS NULL THEN NULL
                    WHEN NEW.end_proposer IS NOT DISTINCT FROM OLD.end_proposer THEN OLD.end_asked_at
                    ELSE now()
                END;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER series_end_written_by_the_release_before BEFORE UPDATE ON series "
        "FOR EACH ROW EXECUTE FUNCTION series_end_written_by_the_release_before()"
    )
