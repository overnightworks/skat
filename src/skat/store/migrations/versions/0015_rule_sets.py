"""A person's saved rule sets: each belongs to one account and holds the table options a table is opened with, in
the columns `tables` keeps them in; no table refers to a set.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"

SAYERS = ("any-opponent", "bidders-only")
REACHES = ("kontra-re", "kontra-re-standings", "up-to-hirsch")
DEADLINES = ("own-card", "first-card")


def _is_one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def upgrade() -> None:
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("owner_account", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("show_running_points", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kontra_sayer", sa.Text()),
        sa.Column("kontra_reach", sa.Text()),
        sa.Column("kontra_deadline", sa.Text()),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="rule_sets_name_is_a_name"),
        sa.CheckConstraint(
            "num_nonnulls(kontra_sayer, kontra_reach, kontra_deadline) IN (0, 3)",
            name="rule_sets_kontra_is_all_or_nothing",
        ),
        sa.CheckConstraint(_is_one_of("kontra_sayer", SAYERS), name="rule_sets_kontra_sayer_is_a_sayer"),
        sa.CheckConstraint(_is_one_of("kontra_reach", REACHES), name="rule_sets_kontra_reach_is_a_reach"),
        sa.CheckConstraint(_is_one_of("kontra_deadline", DEADLINES), name="rule_sets_kontra_deadline_is_a_deadline"),
        sa.UniqueConstraint("owner_account", "name", name="rule_sets_one_name_per_owner"),
    )
