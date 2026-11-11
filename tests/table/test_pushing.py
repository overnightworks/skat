import pytest

from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import PushingRule
from skat.table.records import CreateTable, RamschOccasion, RamschSetting, TableOptions
from skat.table.rules import create_payload

RECKONING = RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120)


def ramsch(pushing=None):
    return TableOptions(ramsch=RamschSetting(RamschOccasion.PASSED_IN, RECKONING, pushing))


class TestTheCreateReceipt:
    def test_a_ramsch_without_pushing_keeps_the_payload_it_had(self):
        assert create_payload(CreateTable("command-1", 3, ramsch())) == (
            '{"series_length":3,"ramsch":{"durchmarsch":"wins-120","jungfrau":"doubles-loser",'
            '"occasion":"passed-in","scoring":"points"}}'
        )

    @pytest.mark.parametrize("rule", list(PushingRule))
    def test_a_pushing_rule_joins_the_ramsch_member_between_the_occasion_and_the_scoring(self, rule):
        assert create_payload(CreateTable("command-1", 3, ramsch(rule))) == (
            '{"series_length":3,"ramsch":{"durchmarsch":"wins-120","jungfrau":"doubles-loser",'
            f'"occasion":"passed-in","pushing":{{"rule":"{rule.value}"}},"scoring":"points"}}}}'
        )
