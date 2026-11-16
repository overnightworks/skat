"""A series and a rule set hold the two special rules of giving up, each a switch; every series and set that exists
plays both off, the ISkO's give-up.
"""

from alembic import op

revision = "0050"
down_revision = "0049"


def upgrade() -> None:
    for table in ("series", "rule_sets"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN give_up_partner_agrees boolean NOT NULL DEFAULT false,"
            " ADD COLUMN give_up_any_time boolean NOT NULL DEFAULT false"
        )
