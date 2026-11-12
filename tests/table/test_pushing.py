from dataclasses import replace

import pytest

from skat.engine.cards import Card, Rank, Suit
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import GrandHandRule, PushingRule
from skat.table.pushing import PushingCommand, PushingKind, pushing_payload
from skat.table.records import CreateTable, RamschOccasion, RamschSetting, TableOptions
from skat.table.rules import create_payload

RECKONING = RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120)


def ramsch(pushing=None, grand_hand=GrandHandRule.OFF):
    return TableOptions(ramsch=RamschSetting(RamschOccasion.PASSED_IN, RECKONING, pushing, grand_hand))


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

    def test_a_grand_hand_that_is_off_keeps_the_payload_and_one_that_is_allowed_adds_its_member(self):
        off = create_payload(CreateTable("command-1", 3, ramsch(PushingRule.JACKS_STAY, GrandHandRule.OFF)))
        allowed = create_payload(CreateTable("command-1", 3, ramsch(PushingRule.JACKS_STAY, GrandHandRule.ALLOWED)))

        assert off == create_payload(CreateTable("command-1", 3, ramsch(PushingRule.JACKS_STAY)))
        assert allowed.count('"pushing":{"grand_hand":"allowed","rule":"jacks-stay"}') == 1


class TestTheStepsReceipt:
    def test_the_kind_the_cards_and_the_version_make_the_payload(self):
        king, ace, queen = (Card(Suit.KARO, rank) for rank in (Rank.KING, Rank.ACE, Rank.QUEEN))
        command = PushingCommand("command-1", "table", 5, PushingKind.PUT_BACK, (king, ace))

        payloads = {
            pushing_payload(command),
            pushing_payload(replace(command, version=6)),
            pushing_payload(replace(command, kind=PushingKind.PUSH, cards=())),
            pushing_payload(replace(command, kind=PushingKind.GRAND_HAND, cards=())),
            pushing_payload(replace(command, cards=(king, queen))),
        }

        assert len(payloads) == 5
