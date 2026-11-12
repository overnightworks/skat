import secrets

import pytest

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.engine.deal import Position, positions_from
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import PushingRule
from skat.store.migrate import migrate
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.pushing import PushingCommand, PushingKind
from skat.table.records import RamschOccasion, RamschSetting, RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet
from skat.table.service import TableService
from tests.support.migrations import upgrade_to
from tests.support.rule_set_rows import a_set, row_count, save, sets_of
from tests.support.stored_game import nobody_connected, person, seated_table_id

pytestmark = pytest.mark.postgres

SET_NAME = "Felix"
BEFORE_THE_PUSHING_VALUE = "0031"
KONTRA = KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD)
BOCK = BockOptions(
    frozenset({BockTrigger.SIXTY_SIXTY, BockTrigger.WON_GRAND_HAND, BockTrigger.LOST_AFTER_KONTRA, BockTrigger.RE}),
    BockOverlap.APPEND,
)
RAMSCH = RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120)
FELIX_WITHOUT_PUSHING = TableOptions(
    show_running_points=False,
    kontra=KONTRA,
    bock=BOCK,
    ramsch=RamschSetting(RamschOccasion.PASSED_IN, RAMSCH),
)
FELIX_OPTIONS = TableOptions(
    show_running_points=False,
    kontra=KONTRA,
    bock=BOCK,
    ramsch=RamschSetting(RamschOccasion.PASSED_IN, RAMSCH, PushingRule.JACKS_STAY),
)


@pytest.fixture
def before_the_pushing_value(unmigrated_engine):
    upgrade_to(unmigrated_engine, BEFORE_THE_PUSHING_VALUE)
    return unmigrated_engine


def test_a_migration_without_the_operator_account_leaves_an_existing_felix_and_does_not_fail(
    before_the_pushing_value, operator_account_id
):
    earlier = a_set(operator_account_id, SET_NAME, FELIX_WITHOUT_PUSHING)
    save(before_the_pushing_value, earlier)

    migrate(before_the_pushing_value, operator_account_id=None)

    assert sets_of(before_the_pushing_value, operator_account_id) == (earlier,)


def test_the_operator_account_gets_felix_with_the_pushing_rule_and_the_earlier_values(
    before_the_pushing_value, operator_account_id
):
    migrate(before_the_pushing_value, operator_account_id=operator_account_id)

    [felix] = sets_of(before_the_pushing_value, operator_account_id)
    assert (felix.name, felix.options) == (SET_NAME, FELIX_OPTIONS)
    assert RuleSetId.parse(felix.id.value) == felix.id


def test_a_fresh_database_taken_to_head_holds_one_felix_with_the_pushing_rule(unmigrated_engine, operator_account_id):
    migrate(unmigrated_engine, operator_account_id=operator_account_id)

    [felix] = sets_of(unmigrated_engine, operator_account_id)
    assert (felix.name, felix.options) == (SET_NAME, FELIX_OPTIONS)
    assert row_count(unmigrated_engine) == 1


def test_the_felix_without_pushing_is_replaced_keeping_its_id(before_the_pushing_value, operator_account_id):
    earlier = a_set(operator_account_id, SET_NAME, FELIX_WITHOUT_PUSHING)
    save(before_the_pushing_value, earlier)

    migrate(before_the_pushing_value, operator_account_id=operator_account_id)

    replaced = RuleSet(earlier.id, operator_account_id, SET_NAME, FELIX_OPTIONS)
    assert sets_of(before_the_pushing_value, operator_account_id) == (replaced,)


def test_another_name_of_the_account_and_another_accounts_felix_stay_untouched(
    before_the_pushing_value, operator_account_id
):
    other_name = a_set(operator_account_id, "Abend")
    others_felix = a_set(f"account-{secrets.token_hex(8)}", SET_NAME)
    save(before_the_pushing_value, other_name)
    save(before_the_pushing_value, others_felix)

    migrate(before_the_pushing_value, operator_account_id=operator_account_id)

    assert sets_of(before_the_pushing_value, others_felix.owner_account) == (others_felix,)
    by_name = {rule_set.name: rule_set for rule_set in sets_of(before_the_pushing_value, operator_account_id)}
    assert by_name["Abend"] == other_name
    assert row_count(before_the_pushing_value) == 3


def test_a_table_opened_with_the_sets_options_answers_them_and_plays_the_stage_of_pushing(
    before_the_pushing_value, operator_account_id, stored
):
    migrate(before_the_pushing_value, operator_account_id=operator_account_id)
    [felix] = sets_of(before_the_pushing_value, operator_account_id)
    transactions = PostgresTableTransactions(before_the_pushing_value)
    service = TableService(transactions)
    table_id = seated_table_id(service, felix.options)
    by_seat = {1: person("Anna"), 2: person("Ben"), 3: person("Cleo")}
    actors = {
        position: by_seat[seat] for seat, position in positions_from(stored(transactions, table_id).dealer).items()
    }
    for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND):
        version = stored(transactions, table_id).version
        command = AuctionCommand(f"pass-{position.value}", table_id, version, AuctionAction.PASS, None)
        service.take_auction_step(actors[position], command, nobody_connected())

    record = stored(transactions, table_id)
    take = PushingCommand("take", table_id, record.version, PushingKind.TAKE, ())
    result = service.take_pushing_step(actors[Position.FOREHAND], take, nobody_connected())

    assert record.options == FELIX_OPTIONS
    assert result.refusal is None
