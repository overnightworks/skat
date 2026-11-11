from sqlalchemy import text

from skat.store.rule_sets import PostgresRuleSets
from skat.table.records import RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet


def sets_of(engine, account_id):
    with PostgresRuleSets(engine).begin() as transaction:
        return transaction.sets_of(account_id)


def save(engine, rule_set):
    with PostgresRuleSets(engine).begin() as transaction:
        transaction.add(rule_set)


OTHER_OPTIONS = TableOptions(show_running_points=True)


def a_set(owner, name, options=OTHER_OPTIONS):
    return RuleSet(RuleSetId.random(), owner, name, options)


def row_count(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM rule_sets")).scalar_one()
