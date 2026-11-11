"""The operator's rule set „Felix“ is installed on his account, or replaced there keeping its id.

The account id comes from the config attributes `migrate` sets; a deployment that names no operator gets no row. The
set holds no Ramsch: a table with Ramsch does not deal Bock rounds, and „Felix“ holds Bock.
"""

import secrets

import sqlalchemy as sa
from alembic import context, op

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
    columns = ", ".join(OPTIONS)
    values = ", ".join(f":{column}" for column in OPTIONS)
    replacements = ", ".join(f"{column} = EXCLUDED.{column}" for column in OPTIONS)
    statement = sa.text(
        f"INSERT INTO rule_sets (id, owner_account, name, {columns}) "  # noqa: S608 - only this file's fixed column names reach this text
        f"VALUES (:id, :owner_account, :name, {values}) "
        f"ON CONFLICT (owner_account, name) DO UPDATE SET {replacements}"
    ).bindparams(sa.bindparam("bock_triggers", type_=sa.ARRAY(sa.Text())))
    op.get_bind().execute(
        statement, {"id": secrets.token_hex(16), "owner_account": operator_account_id, "name": SET_NAME, **OPTIONS}
    )


def upgrade() -> None:
    operator_account_id = context.config.attributes.get("operator_account_id")
    if operator_account_id is not None:
        _install(operator_account_id)
