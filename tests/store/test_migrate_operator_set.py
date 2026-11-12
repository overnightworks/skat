import pytest

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.store.migrations.operator_set import install_operator_set
from skat.table.records import RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet
from tests.support.rule_set_rows import a_set, row_count, save, sets_of

pytestmark = pytest.mark.postgres


@pytest.fixture
def set_name():
    return "Abend"


@pytest.fixture
def with_bock():
    """The option values as a revision writes them: its column names to the database's own representations."""
    return {
        "show_running_points": True,
        "bock_triggers": ["re", "sixty-sixty"],
        "bock_overlap": "append",
    }


@pytest.fixture
def with_bock_options():
    """The options the store reads the `with_bock` values back as."""
    return TableOptions(
        show_running_points=True,
        bock=BockOptions(frozenset({BockTrigger.RE, BockTrigger.SIXTY_SIXTY}), BockOverlap.APPEND),
    )


@pytest.fixture
def install(engine, set_name):
    def install_into(account_id, options):
        with engine.begin() as connection:
            install_operator_set(connection, account_id, set_name, options)

    return install_into


def test_a_list_value_binds_and_reads_back_without_naming_its_column(
    engine, operator_account_id, set_name, with_bock, with_bock_options, install
):
    install(operator_account_id, with_bock)

    [installed] = sets_of(engine, operator_account_id)
    assert (installed.name, installed.options) == (set_name, with_bock_options)
    assert RuleSetId.parse(installed.id.value) == installed.id


def test_a_set_of_that_name_is_replaced_keeping_its_id(
    engine, operator_account_id, set_name, with_bock, with_bock_options, install
):
    earlier = a_set(operator_account_id, set_name)
    save(engine, earlier)

    install(operator_account_id, with_bock)

    assert sets_of(engine, operator_account_id) == (
        RuleSet(earlier.id, operator_account_id, set_name, with_bock_options),
    )
    assert row_count(engine) == 1
