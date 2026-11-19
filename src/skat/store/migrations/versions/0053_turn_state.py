"""A seat's last `set_turn_state` statement lives on its chair: the stated outcome, whether a turn runs, the account
that stated it and the time.

Expand only: nullable columns, so the release before this one serves on the new schema. It does not name them when
it frees a chair, so a value it leaves behind is read only while its account still sits there.
"""

from alembic import op

revision = "0053"
down_revision = "0051"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chairs"
        " ADD COLUMN turn_state_account text,"
        " ADD COLUMN turn_state_stopped text,"
        " ADD COLUMN turn_state_thinking boolean,"
        " ADD COLUMN turn_state_at timestamptz"
    )
