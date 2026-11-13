"""An invitation an accept ended stays in the book, with how it ended, until its caller was told.

Expand only: the column is nullable and an invitation stored before reads as one that has not ended by an accept, so it
runs out unanswered.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade() -> None:
    op.add_column("member_book", sa.Column("ended_outcome", sa.Text()))
    op.create_check_constraint(
        "member_book_an_outcome_ends_an_invitation", "member_book", "ended_outcome IS NULL OR invitation_id IS NOT NULL"
    )
