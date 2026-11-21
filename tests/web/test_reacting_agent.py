"""A seated agent throws a reaction as a person does, through `throw_reaction`, and the table's pages read it."""

import pytest

from skat.table.reacting import REACTIONS_PER_WINDOW, Reaction
from skat.web.mcp import THROW_REACTION_TOOL
from tests.web.support.playing import REARHAND
from tests.web.support.skat import running_skat

skat = pytest.fixture(name="skat")(running_skat)


class TestAnAgentThrowsAReaction:
    def test_the_table_answers_every_page_with_the_throw_by_the_agents_seat_and_name(self, agent, middlehand_auction):
        table = middlehand_auction

        thrown = agent.call(THROW_REACTION_TOOL, table_id=table.table_id, reaction=str(Reaction.CHEERS))
        read = table.read_as(table.at[REARHAND]).json()

        assert thrown.is_error is False
        assert read["reactions"] == [
            {
                "number": 1,
                "reaction": "cheers",
                "by_seat": next(chair["seat"] for chair in read["chairs"] if chair["occupant_kind"] == "agent"),
                "by_name": next(
                    chair["occupant_name"] for chair in read["chairs"] if chair["occupant_kind"] == "agent"
                ),
            }
        ]

    def test_too_many_throws_in_a_row_are_refused_as_they_are_for_a_person(self, agent, middlehand_auction):
        table = middlehand_auction

        answers = [
            agent.call(THROW_REACTION_TOOL, table_id=table.table_id, reaction=str(Reaction.CLAP))
            for _ in range(REACTIONS_PER_WINDOW + 1)
        ]

        assert [answer.is_error for answer in answers] == [False] * REACTIONS_PER_WINDOW + [True]
        assert answers[-1].json()["reason"] == "too-fast"
