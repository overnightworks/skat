import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import inspect

if TYPE_CHECKING:
    from sqlalchemy import Engine

IGNORED_TABLES = frozenset({"alembic_version"})

# Only a check that is nothing but one column against a list of text values is read as an admission; any other form
# (an OR, `num_nonnulls`, a check beside other conditions) is skipped, so that a `<>` inside one is no hold-back.
_LISTED = re.compile(r"\(?(?P<column>\w+) (?:= ANY \(|<@ )ARRAY\[(?P<values>[^\]]*)\]\)?\)?")
_HELD_BACK = re.compile(r"\(?(?P<column>\w+) <> ALL \(ARRAY\[(?P<values>[^\]]*)\]\)\)?")
_QUOTED = re.compile(r"'([^']*)'")


@dataclass(frozen=True)
class Admission:
    """What the checks on one column let a release write: the values its list admits and those it holds back."""

    listed: frozenset[str]
    held_back: frozenset[str]

    @property
    def writable(self) -> frozenset[str]:
        return self.listed - self.held_back


@dataclass(frozen=True)
class ColumnFacts:
    type: str
    not_null: bool
    default: str | None


@dataclass(frozen=True, order=True)
class UniqueFacts:
    """A unique constraint or index by what it restricts: its keys (columns or expressions) and the predicate of a
    partial one, so that an unconditional index beside a partial one on the same columns is a new restriction.
    """

    keys: tuple[str, ...]
    predicate: str = ""

    def describe(self) -> str:
        return f"{self.keys} where {self.predicate}" if self.predicate else str(self.keys)


@dataclass(frozen=True)
class TableFacts:
    columns: dict[str, ColumnFacts]
    primary_key: tuple[str, ...]
    foreign_keys: frozenset[tuple[tuple[str, ...], str, tuple[str, ...]]]
    uniques: frozenset[UniqueFacts]
    checks: frozenset[str]

    def admissions(self) -> dict[str, Admission]:
        """Per column with a list of admitted values: that list and what is held back from it."""
        listed: dict[str, frozenset[str]] = {}
        held_back: dict[str, frozenset[str]] = {}
        for check in self.checks:
            if found := _LISTED.fullmatch(check):
                column, values = found["column"], frozenset(_QUOTED.findall(found["values"]))
                listed[column] = listed.get(column, values) & values
            elif found := _HELD_BACK.fullmatch(check):
                column = found["column"]
                held_back[column] = held_back.get(column, frozenset()) | frozenset(_QUOTED.findall(found["values"]))
        return {column: Admission(values, held_back.get(column, frozenset())) for column, values in listed.items()}


def schema_facts(engine: Engine) -> dict[str, TableFacts]:
    """What an older revision's code can rely on in each table, as reflected from the database; constraint names
    are left out, because a rename changes nothing the code relies on.
    """
    inspector = inspect(engine)
    facts: dict[str, TableFacts] = {}
    for table in set(inspector.get_table_names()) - IGNORED_TABLES:
        unique_indexes = {
            UniqueFacts(
                tuple(index.get("expressions") or index["column_names"]),
                index["dialect_options"].get("postgresql_where") or "",
            )
            for index in inspector.get_indexes(table)
            if index["unique"]
        }
        constraints = {UniqueFacts(tuple(unique["column_names"])) for unique in inspector.get_unique_constraints(table)}
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
        f"a unique constraint or index on {unique.describe()} is new"
        for unique in sorted(after.uniques - before.uniques)
    )
    found.extend(
        f"the check {check} is new"
        for check in sorted(after.checks - before.checks)
        if not _only_widens_what_is_read(check, before)
    )
    return found


def _only_widens_what_is_read(check: str, before: TableFacts) -> bool:
    """A new list that keeps every value of the old one, or a hold-back of values the old one did not admit."""
    if found := _LISTED.fullmatch(check):
        old = before.admissions().get(found["column"])
        return old is not None and old.listed <= frozenset(_QUOTED.findall(found["values"]))
    if found := _HELD_BACK.fullmatch(check):
        old = before.admissions().get(found["column"])
        return old is not None and not old.listed & frozenset(_QUOTED.findall(found["values"]))
    return False


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


def admissions(facts: dict[str, TableFacts]) -> dict[tuple[str, str], Admission]:
    """The admission of every table and column that has one."""
    return {
        (table, column): admission
        for table, table_facts in facts.items()
        for column, admission in table_facts.admissions().items()
    }


def unreadable_by_the_release_before(before: dict[str, TableFacts], after: dict[str, TableFacts]) -> list[str]:
    """The values `after` lets a release write that the schema `before` does not list as read, one text each."""
    old_admissions = admissions(before)
    return [
        f"table {table}: column {column} admits {value!r}, which the release before does not read; list it and "
        f"hold it back (`held_back`) in this release, and write it in the next"
        for (table, column), admission in sorted(admissions(after).items())
        if (old := old_admissions.get((table, column)))
        for value in sorted(admission.writable - old.listed)
    ]
