from sqlalchemy import insert, literal, select, text

from skat.store.rule_sets import PostgresRuleSets
from skat.store.schema import option_values, options_of, rule_sets
from skat.table.records import RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet

# The column the pushing revision added: a database before it has none.
NEWER_COLUMN = "ramsch_pushing"


def sets_of(engine, account_id):
    with PostgresRuleSets(engine).begin() as transaction:
        return transaction.sets_of(account_id)


def save_before_pushing(engine, rule_set):
    """Write a set into a database before the pushing revision, whose rule sets have no pushing column."""
    values = {**option_values(rule_set.options)}
    del values[NEWER_COLUMN]
    with engine.begin() as connection:
        connection.execute(
            insert(rule_sets).values(
                id=rule_set.id.value, owner_account=rule_set.owner_account, name=rule_set.name, **values
            )
        )


def sets_before_pushing(engine, account_id):
    """The sets a database before the pushing revision holds, read with the columns it has; none plays pushing."""
    older = [column for column in rule_sets.c if column.name != NEWER_COLUMN]
    with engine.connect() as connection:
        rows = connection.execute(
            select(*older, literal(None).label(NEWER_COLUMN)).where(rule_sets.c.owner_account == account_id)
        )
        return tuple(RuleSet(RuleSetId(row.id), row.owner_account, row.name, options_of(row)) for row in rows)


OTHER_OPTIONS = TableOptions(show_running_points=True)


def a_set(owner, name, options=OTHER_OPTIONS):
    return RuleSet(RuleSetId.random(), owner, name, options)


def row_count(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM rule_sets")).scalar_one()
