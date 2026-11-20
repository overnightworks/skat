"""A series that is over stores the instant of its first „Neue Serie“, from which a silent seat counts as no. A
table that „Aufhören“ or a silent seat ends stores the reason the release before reads, `closed` with no name.
"""

from alembic import op

revision = "0055"
down_revision = "0054"


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN new_series_asked_at timestamptz")
