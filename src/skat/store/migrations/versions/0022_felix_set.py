"""The operator's rule set „Felix“ is installed on his account, or replaced there keeping its id.

The account id comes from the config attributes `migrate` sets; a deployment that names no operator gets no row. The
set holds no Ramsch: a table with Ramsch does not deal Bock rounds, and „Felix“ holds Bock.
"""

from alembic import context, op

from skat.store.migrations.operator_set import install_operator_set

revision = "0022"
down_revision = "0021"

SET_NAME = "Felix"
OPTIONS = {
    "show_running_points": False,
    "kontra_sayer": "bidders-only",
    "kontra_reach": "up-to-hirsch",
    "kontra_deadline": "own-card",
    "bock_triggers": ["lost-after-kontra", "re", "sixty-sixty", "won-grand-hand"],
    "bock_overlap": "append",
    "ramsch_occasion": None,
    "ramsch_scoring": None,
    "ramsch_jungfrau": None,
    "ramsch_durchmarsch": None,
}


def _install(operator_account_id: str) -> None:
    install_operator_set(op.get_bind(), operator_account_id, SET_NAME, OPTIONS)


def upgrade() -> None:
    operator_account_id = context.config.attributes.get("operator_account_id")
    if operator_account_id is not None:
        _install(operator_account_id)
