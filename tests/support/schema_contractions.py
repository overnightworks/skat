from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import inspect

if TYPE_CHECKING:
    from sqlalchemy import Engine

IGNORED_TABLES = frozenset({"alembic_version"})


@dataclass(frozen=True)
class ColumnFacts:
    type: str
    not_null: bool
    default: str | None


@dataclass(frozen=True)
class TableFacts:
    columns: dict[str, ColumnFacts]
    primary_key: tuple[str, ...]
    foreign_keys: frozenset[tuple[tuple[str, ...], str, tuple[str, ...]]]
    uniques: frozenset[tuple[str, ...]]
    checks: frozenset[str]


def schema_facts(engine: Engine) -> dict[str, TableFacts]:
    """What an older revision's code can rely on in each table, as reflected from the database; constraint names
    are left out, because a rename changes nothing the code relies on.
    """
    inspector = inspect(engine)
    facts: dict[str, TableFacts] = {}
    for table in set(inspector.get_table_names()) - IGNORED_TABLES:
        unique_indexes = {tuple(index["column_names"]) for index in inspector.get_indexes(table) if index["unique"]}
        constraints = {tuple(unique["column_names"]) for unique in inspector.get_unique_constraints(table)}
        facts[table] = TableFacts(
            columns={
                column["name"]: ColumnFacts(str(column["type"]), not column["nullable"], column["default"])
                for column in inspector.get_columns(table)
            },
            primary_key=tuple(inspector.get_pk_constraint(table)["constrained_columns"]),
            foreign_keys=frozenset(
                (tuple(key["constrained_columns"]), key["referred_table"], tuple(key["referred_columns"]))
                for key in inspector.get_foreign_keys(table)
            ),
            uniques=frozenset(unique_indexes | constraints),
            checks=frozenset(check["sqltext"] for check in inspector.get_check_constraints(table)),
        )
    return facts


def contractions(before: dict[str, TableFacts], after: dict[str, TableFacts]) -> list[str]:
    """What the step from `before` to `after` takes away from code that still runs on `before`, one text each."""
    found = [f"table {table} is dropped" for table in sorted(before.keys() - after.keys())]
    for table in sorted(before.keys() & after.keys()):
        found.extend(f"table {table}: {problem}" for problem in _table_contractions(before[table], after[table]))
    return found


def _table_contractions(before: TableFacts, after: TableFacts) -> list[str]:
    found = [f"column {name} is dropped" for name in sorted(before.columns.keys() - after.columns.keys())]
    for name, column in after.columns.items():
        found.extend(f"column {name}: {problem}" for problem in _column_contractions(before.columns.get(name), column))
    if before.primary_key != after.primary_key:
        found.append("the primary key changes")
    found.extend(
        f"a foreign key on {columns} is new" for columns, _, _ in sorted(after.foreign_keys - before.foreign_keys)
    )
    found.extend(
        f"a unique constraint or index on {columns} is new" for columns in sorted(after.uniques - before.uniques)
    )
    found.extend(f"the check {check} is new" for check in sorted(after.checks - before.checks))
    return found


def _column_contractions(before: ColumnFacts | None, after: ColumnFacts) -> list[str]:
    if before is None:
        return ["is new and NOT NULL without a default"] if after.not_null and after.default is None else []
    found = []
    if before.type != after.type:
        found.append("changes its type")
    if after.not_null and not before.not_null:
        found.append("becomes NOT NULL")
    if before.default is not None and before.default != after.default:
        found.append("loses or changes its server default")
    return found
