import pytest
from skat.store.migrations.operator_set import install_operator_set

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.table.records import RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet
from tests.support.rule_set_rows import a_set, row_count, save, sets_of

pytestmark = pytest.mark.postgres

SET_NAME = "Abend"
WITH_BOCK = {
    "show_running_points": True,
    "bock_triggers": ["re", "sixty-sixty"],
    "bock_overlap": "append",
}
WITH_BOCK_OPTIONS = TableOptions(
    show_running_points=True,
    bock=BockOptions(frozenset({BockTrigger.RE, BockTrigger.SIXTY_SIXTY}), BockOverlap.APPEND),
)


def install(engine, account_id, options):
    with engine.begin() as connection:
        install_operator_set(connection, account_id, SET_NAME, options)


def test_a_list_value_binds_and_reads_back_without_naming_its_column(engine, operator_account_id):
    install(engine, operator_account_id, WITH_BOCK)

    [installed] = sets_of(engine, operator_account_id)
    assert (installed.name, installed.options) == (SET_NAME, WITH_BOCK_OPTIONS)
    assert RuleSetId.parse(installed.id.value) == installed.id


def test_a_set_of_that_name_is_replaced_keeping_its_id(engine, operator_account_id):
    earlier = a_set(operator_account_id, SET_NAME)
    save(engine, earlier)

    install(engine, operator_account_id, WITH_BOCK)

    assert sets_of(engine, operator_account_id) == (
        RuleSet(earlier.id, operator_account_id, SET_NAME, WITH_BOCK_OPTIONS),
    )
    assert row_count(engine) == 1
