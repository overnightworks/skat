from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from skat.store.schema import option_values, options_of, rule_sets
from skat.store.tables import UNIQUE_VIOLATION
from skat.table.records import RuleSetId
from skat.table.rule_sets import DuplicateRuleSetError, RuleSet, RuleSetTransaction

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Connection, Engine


class _PostgresRuleSetTransaction:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def sets_of(self, owner_account: str) -> tuple[RuleSet, ...]:
        return tuple(
            RuleSet(RuleSetId(row.id), row.owner_account, row.name, options_of(row))
            for row in self._connection.execute(select(rule_sets).where(rule_sets.c.owner_account == owner_account))
        )

    def add(self, rule_set: RuleSet) -> None:
        try:
            self._connection.execute(
                insert(rule_sets).values(
                    id=rule_set.id.value,
                    owner_account=rule_set.owner_account,
                    name=rule_set.name,
                    **option_values(rule_set.options),
                )
            )
        except IntegrityError as failure:
            if getattr(failure.orig, "sqlstate", None) == UNIQUE_VIOLATION:
                raise DuplicateRuleSetError from failure
            raise  # pragma: no cover

    def delete(self, owner_account: str, rule_set_id: RuleSetId) -> bool:
        deleted = self._connection.execute(
            delete(rule_sets).where(rule_sets.c.id == rule_set_id.value, rule_sets.c.owner_account == owner_account)
        )
        return deleted.rowcount == 1


class PostgresRuleSets:
    """One Postgres transaction per `begin`: it commits when the block ends and rolls back when it raises."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Generator[RuleSetTransaction]:
        with self._engine.begin() as connection:
            yield _PostgresRuleSetTransaction(connection)
