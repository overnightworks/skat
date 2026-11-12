import secrets

import pytest

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.table.records import RamschOccasion, RamschSetting, RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet
from tests.support.migrations import upgrade_to
from tests.support.rule_set_rows import a_set, row_count, save_before_pushing, sets_before_pushing

pytestmark = pytest.mark.postgres

SET_NAME = "Felix"
BEFORE_THE_RAMSCH_VALUES = "0022"
THE_RAMSCH_VALUES = "0023"
KONTRA = KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD)
BOCK = BockOptions(
    frozenset({BockTrigger.SIXTY_SIXTY, BockTrigger.WON_GRAND_HAND, BockTrigger.LOST_AFTER_KONTRA, BockTrigger.RE}),
    BockOverlap.APPEND,
)
FELIX_WITHOUT_RAMSCH = TableOptions(show_running_points=False, kontra=KONTRA, bock=BOCK)
FELIX_OPTIONS = TableOptions(
    show_running_points=False,
    kontra=KONTRA,
    bock=BOCK,
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120),
    ),
)


@pytest.fixture
def before_the_ramsch_values(unmigrated_engine):
    upgrade_to(unmigrated_engine, BEFORE_THE_RAMSCH_VALUES)
    return unmigrated_engine


def test_a_migration_without_the_operator_account_leaves_an_existing_felix_and_does_not_fail(
    before_the_ramsch_values, operator_account_id
):
    earlier = a_set(operator_account_id, SET_NAME, FELIX_WITHOUT_RAMSCH)
    save_before_pushing(before_the_ramsch_values, earlier)

    upgrade_to(before_the_ramsch_values, THE_RAMSCH_VALUES)

    assert sets_before_pushing(before_the_ramsch_values, operator_account_id) == (earlier,)


def test_the_operator_account_gets_the_set_with_kontra_bock_and_ramsch_values_though_it_never_signed_in(
    before_the_ramsch_values, operator_account_id
):
    upgrade_to(before_the_ramsch_values, THE_RAMSCH_VALUES, operator_account_id)

    [felix] = sets_before_pushing(before_the_ramsch_values, operator_account_id)
    assert (felix.name, felix.options) == (SET_NAME, FELIX_OPTIONS)
    assert RuleSetId.parse(felix.id.value) == felix.id


def test_the_felix_without_ramsch_is_replaced_keeping_its_id(before_the_ramsch_values, operator_account_id):
    earlier = a_set(operator_account_id, SET_NAME, FELIX_WITHOUT_RAMSCH)
    save_before_pushing(before_the_ramsch_values, earlier)

    upgrade_to(before_the_ramsch_values, THE_RAMSCH_VALUES, operator_account_id)

    replaced = RuleSet(earlier.id, operator_account_id, SET_NAME, FELIX_OPTIONS)
    assert sets_before_pushing(before_the_ramsch_values, operator_account_id) == (replaced,)


def test_another_name_of_the_account_and_another_accounts_felix_stay_untouched(
    before_the_ramsch_values, operator_account_id
):
    other_name = a_set(operator_account_id, "Abend")
    others_felix = a_set(f"account-{secrets.token_hex(8)}", SET_NAME)
    save_before_pushing(before_the_ramsch_values, other_name)
    save_before_pushing(before_the_ramsch_values, others_felix)

    upgrade_to(before_the_ramsch_values, THE_RAMSCH_VALUES, operator_account_id)

    assert sets_before_pushing(before_the_ramsch_values, others_felix.owner_account) == (others_felix,)
    by_name = {
        rule_set.name: rule_set for rule_set in sets_before_pushing(before_the_ramsch_values, operator_account_id)
    }
    assert by_name["Abend"] == other_name
    assert row_count(before_the_ramsch_values) == 3
