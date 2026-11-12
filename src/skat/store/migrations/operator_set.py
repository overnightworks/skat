"""The shared write of the operator's rule set: a revision of a version hands it the values it holds."""

import secrets
from typing import TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from collections.abc import Mapping


def install_operator_set(connection: sa.Connection, account_id: str, name: str, options: Mapping[str, object]) -> None:
    """Insert the set `name` of `account_id` with the option columns `options` names, or replace those columns on the
    set it already holds, keeping its id. A column the revision does not name is none of its business.
    """
    columns = ", ".join(options)
    values = ", ".join(f":{column}" for column in options)
    replacements = ", ".join(f"{column} = EXCLUDED.{column}" for column in options)
    statement = sa.text(
        f"INSERT INTO rule_sets (id, owner_account, name, {columns}) "  # noqa: S608 - only a revision's fixed column names reach this text
        f"VALUES (:id, :owner_account, :name, {values}) "
        f"ON CONFLICT (owner_account, name) DO UPDATE SET {replacements}"
    )
    connection.execute(statement, {"id": secrets.token_hex(16), "owner_account": account_id, "name": name, **options})
