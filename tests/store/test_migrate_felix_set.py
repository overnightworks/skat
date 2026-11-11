import secrets

import pytest
from sqlalchemy import text

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.store.rule_sets import PostgresRuleSets
from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CreateTable, RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet
from skat.table.service import TableService
from tests.support.migrations import upgrade_to

pytestmark = pytest.mark.postgres

SET_NAME = "Felix"
BEFORE_THE_SET = "0021"
THE_SET = "0022"
FELIX_OPTIONS = TableOptions(
    show_running_points=False,
    kontra=KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD),
    bock=BockOptions(
        frozenset({BockTrigger.SIXTY_SIXTY, BockTrigger.WON_GRAND_HAND, BockTrigger.LOST_AFTER_KONTRA, BockTrigger.RE}),
        BockOverlap.APPEND,
    ),
)
OTHER_OPTIONS = TableOptions(show_running_points=True)


@pytest.fixture
def operator_account_id():
    return f"account-{secrets.token_hex(8)}"


@pytest.fixture
def before_the_set(unmigrated_engine):
    upgrade_to(unmigrated_engine, BEFORE_THE_SET)
    return unmigrated_engine


def sets_of(engine, account_id):
    with PostgresRuleSets(engine).begin() as transaction:
        return transaction.sets_of(account_id)


def save(engine, rule_set):
    with PostgresRuleSets(engine).begin() as transaction:
        transaction.add(rule_set)


def a_set(owner, name, options=OTHER_OPTIONS):
    return RuleSet(RuleSetId.random(), owner, name, options)


def row_count(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM rule_sets")).scalar_one()


def test_a_migration_without_the_operator_account_inserts_nothing_and_does_not_fail(before_the_set):
    upgrade_to(before_the_set, THE_SET)

    assert row_count(before_the_set) == 0


def test_the_operator_account_gets_the_set_with_the_ruled_options_though_it_never_signed_in(
    before_the_set, operator_account_id
):
    upgrade_to(before_the_set, THE_SET, operator_account_id)

    [felix] = sets_of(before_the_set, operator_account_id)
    assert (felix.name, felix.options) == (SET_NAME, FELIX_OPTIONS)
    assert RuleSetId.parse(felix.id.value) == felix.id


def test_a_felix_the_account_already_holds_is_replaced_keeping_its_id(before_the_set, operator_account_id):
    own = a_set(operator_account_id, SET_NAME)
    save(before_the_set, own)

    upgrade_to(before_the_set, THE_SET, operator_account_id)

    replaced = RuleSet(own.id, operator_account_id, SET_NAME, FELIX_OPTIONS)
    assert sets_of(before_the_set, operator_account_id) == (replaced,)


def test_another_name_of_the_account_and_another_accounts_felix_stay_untouched(before_the_set, operator_account_id):
    other_name = a_set(operator_account_id, "Abend")
    others_felix = a_set(f"account-{secrets.token_hex(8)}", SET_NAME)
    save(before_the_set, other_name)
    save(before_the_set, others_felix)

    upgrade_to(before_the_set, THE_SET, operator_account_id)

    assert sets_of(before_the_set, others_felix.owner_account) == (others_felix,)
    assert {rule_set.name: rule_set for rule_set in sets_of(before_the_set, operator_account_id)}["Abend"] == other_name
    assert row_count(before_the_set) == 3


def test_a_table_opened_with_the_sets_options_answers_exactly_them(before_the_set, operator_account_id):
    upgrade_to(before_the_set, THE_SET, operator_account_id)
    [felix] = sets_of(before_the_set, operator_account_id)
    actor = Actor(account_id=operator_account_id, display_name="Operator")
    service = TableService(PostgresTableTransactions(before_the_set))

    table = service.create(actor, CreateTable(command_id="open", options=felix.options))

    assert table.options == FELIX_OPTIONS
