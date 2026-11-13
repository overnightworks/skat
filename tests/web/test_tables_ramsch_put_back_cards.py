import pytest

from skat.engine.cards import Rank
from tests.support.payload_cards import cards_in, wire_cards
from tests.web.support.playing import FOREHAND, MIDDLEHAND, PLAIN_DEAL, REARHAND, cards
from tests.web.support.ramsch_stage import accepted, read, stage_table

TWELVE = (*PLAIN_DEAL.forehand, *PLAIN_DEAL.skat)
WITHOUT_JACKS = tuple(each for each in TWELVE if each.rank is not Rank.JACK)


def named_by(table, position):
    return cards_in(read(table, position)["hand"]["pushing"]["put_back_cards"])


class TestTheCardsThatMayGoBack:
    @pytest.mark.parametrize(
        ("rule", "may_go"),
        [
            pytest.param("jacks-stay", WITHOUT_JACKS, id="jacks-stay"),
            pytest.param("no-doubling", WITHOUT_JACKS, id="no-doubling"),
            pytest.param("jacks-may-go", TWELVE, id="jacks-may-go"),
        ],
    )
    def test_the_taker_is_told_the_cards_its_rule_lets_go_back_and_nobody_else_is_told_any(self, skat, rule, may_go):
        table = stage_table(skat, rule)

        accepted(table, FOREHAND, "take")

        assert named_by(table, FOREHAND) == wire_cards(may_go)
        assert [named_by(table, position) for position in (MIDDLEHAND, REARHAND, None)] == [set(), set(), set()]

    def test_the_next_seat_is_told_none_until_it_takes_and_then_its_own(self, skat):
        table = stage_table(skat, "jacks-may-go")
        accepted(table, FOREHAND, "push")

        before = named_by(table, MIDDLEHAND)
        accepted(table, MIDDLEHAND, "take")

        assert before == set()
        assert named_by(table, MIDDLEHAND) == wire_cards((*PLAIN_DEAL.middlehand, *PLAIN_DEAL.skat))

    def test_the_cards_put_back_leave_the_answer_with_the_turn(self, skat):
        table = stage_table(skat)
        accepted(table, FOREHAND, "take")

        accepted(table, FOREHAND, "put-back", cards("C7 C8"))

        assert [named_by(table, position) for position in (FOREHAND, MIDDLEHAND)] == [set(), set()]
