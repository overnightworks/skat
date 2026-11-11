"""The operator's rule set „Felix“ is replaced on his account, keeping its id, with the Ramsch values added.

The account id comes from the config attributes `migrate` sets; a deployment that names no operator changes nothing.
A table can play Ramsch and Bock together, so the set holds both.
"""

import secrets

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

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
RULE_SETS = sa.table(
    "rule_sets",
    sa.column("id"),
    sa.column("owner_account"),
    sa.column("name"),
    *(sa.column(option, sa.ARRAY(sa.Text()) if option == "bock_triggers" else None) for option in OPTIONS),
)


def _install(operator_account_id: str) -> None:
    values = {"id": secrets.token_hex(16), "owner_account": operator_account_id, "name": SET_NAME, **OPTIONS}
    insertion = postgresql.insert(RULE_SETS).values(values)
    replacement = {column: insertion.excluded[column] for column in OPTIONS}
    op.get_bind().execute(insertion.on_conflict_do_update(index_elements=["owner_account", "name"], set_=replacement))


def upgrade() -> None:
    operator_account_id = context.config.attributes.get("operator_account_id")
    if operator_account_id is not None:
        _install(operator_account_id)
