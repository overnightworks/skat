"""A chair of a running hand names its leaver while it stays open, and nobody once it is taken or the hand ends."""

from dataclasses import replace

import pytest

from skat.table.records import FormerHolder, HandProgress, NewHand
from skat.table.rules import dealt_next, decide_sit, decide_stand
from tests.support.open_chairs import MIDDLEHAND_SEAT, PHASES, REARHAND_SEAT, actor_at, newcomer, sent_away


def stood_up(table, seat):
    decision = decide_stand(table, actor_at(table, seat))
    assert decision.refusal is None
    return decision.table


def name_of(table, seat):
    return actor_at(table, seat).display_name


class TestTheFormerHolder:
    @pytest.mark.parametrize("phase", PHASES)
    def test_a_stand_up_names_the_person_who_left_the_chair(self, phase):
        table = PHASES[phase]()

        freed = stood_up(table, MIDDLEHAND_SEAT)

        assert freed.progress.former_holders == {FormerHolder(MIDDLEHAND_SEAT, name_of(table, MIDDLEHAND_SEAT))}

    @pytest.mark.parametrize("phase", PHASES)
    def test_a_send_away_names_the_agent_who_left_the_chair(self, phase):
        table = PHASES[phase]()

        freed = sent_away(table, REARHAND_SEAT)

        assert freed.progress.former_holders == {FormerHolder(REARHAND_SEAT, name_of(table, REARHAND_SEAT))}

    @pytest.mark.parametrize("phase", PHASES)
    def test_a_sit_takes_the_name_away(self, phase):
        freed = sent_away(PHASES[phase](), REARHAND_SEAT)

        taken = decide_sit(freed, newcomer(), REARHAND_SEAT, None).table

        assert taken.progress.former_holders == frozenset()

    def test_a_second_open_chair_names_its_own_leaver_and_keeps_the_first(self):
        table = PHASES["auction"]()

        two_open = stood_up(stood_up(table, MIDDLEHAND_SEAT), REARHAND_SEAT)

        assert two_open.progress.former_holders == {
            FormerHolder(MIDDLEHAND_SEAT, name_of(table, MIDDLEHAND_SEAT)),
            FormerHolder(REARHAND_SEAT, name_of(table, REARHAND_SEAT)),
        }

    def test_a_sitter_who_leaves_again_names_himself_in_place_of_the_first_leaver(self):
        table = PHASES["auction"]()
        sitter = newcomer(name="Dora")
        taken = decide_sit(stood_up(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table

        left = stood_up(taken, MIDDLEHAND_SEAT)

        assert left.progress.former_holders == {FormerHolder(MIDDLEHAND_SEAT, "Dora")}

    def test_a_stand_up_between_hands_names_nobody(self):
        between = replace(PHASES["auction"](), hand=None, progress=HandProgress())

        assert stood_up(between, MIDDLEHAND_SEAT).progress.former_holders == frozenset()

    def test_the_next_deal_starts_without_a_name(self):
        table = PHASES["auction"]()
        marked = replace(stood_up(table, MIDDLEHAND_SEAT), hand=None)

        dealt = dealt_next(marked, NewHand(1, table.hand))

        assert dealt.progress.former_holders == frozenset()
