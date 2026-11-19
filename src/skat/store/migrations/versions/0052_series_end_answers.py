"""Every seat answers a proposal to end the series, and the proposal's instant is stored: the seats that said yes, the
instant the proposal was made, from which a silent seat counts as no, and the seats whose no ended the last proposal.
The proposer's yes stays in `end_proposer`; `end_accepter` is no longer written, though the release before, which serves
beside this one, still writes it. A proposal standing at the migration gets its yes list and starts its minute now.
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
