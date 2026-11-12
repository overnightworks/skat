"""The operator's rule set „Felix“ is replaced on his account, keeping its id, with the Ramsch values added.

The account id comes from the config attributes `migrate` sets; a deployment that names no operator changes nothing.
A table can play Ramsch and Bock together, so the set holds both.
"""

from alembic import context, op

from skat.store.migrations.operator_set import install_operator_set

revision = "0023"
down_revision = "0022"

SET_NAME = "Felix"
OPTIONS = {
    "show_running_points": False,
    "kontra_sayer": "bidders-only",
    "kontra_reach": "up-to-hirsch",
    "kontra_deadline": "own-card",
    "bock_triggers": ["lost-after-kontra", "re", "sixty-sixty", "won-grand-hand"],
    "bock_overlap": "append",
    "ramsch_occasion": "passed-in",
    "ramsch_scoring": "points",
    "ramsch_jungfrau": "doubles-loser",
    "ramsch_durchmarsch": "wins-120",
}


def _install(operator_account_id: str) -> None:
    install_operator_set(op.get_bind(), operator_account_id, SET_NAME, OPTIONS)


def upgrade() -> None:
    operator_account_id = context.config.attributes.get("operator_account_id")
    if operator_account_id is not None:
        _install(operator_account_id)
