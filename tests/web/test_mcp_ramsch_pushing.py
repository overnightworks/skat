import json

import pytest

from skat.web.mcp import (
    AUCTION_PASS_TOOL,
    RAMSCH_DECLARE_GRAND_HAND_TOOL,
    RAMSCH_PUSH_SKAT_TOOL,
    RAMSCH_PUT_BACK_CARDS_TOOL,
    RAMSCH_TAKE_SKAT_TOOL,
)
from skat.web.pushing import TABLE_PUSHING_PUSH_SUFFIX
from tests.support.payload_cards import with_known_deal
from tests.web.support.playing import FOREHAND, MIDDLEHAND, PLAIN_DEAL, PLAIN_HAND, REARHAND, Table, card_body, cards
from tests.web.support.skat import Skat

PUSHING = {
    "ramsch": {
        "occasion": "passed-in",
        "scoring": "points",
        "jungfrau": "doubles-loser",
        "durchmarsch": "wins-120",
        "pushing": {"rule": "jacks-stay"},
    }
}
GRAND_HAND_ALLOWED = {"ramsch": {**PUSHING["ramsch"], "pushing": {"rule": "jacks-stay", "grand_hand": "allowed"}}}
PUSHING_TOOLS = (
    RAMSCH_TAKE_SKAT_TOOL,
    RAMSCH_PUT_BACK_CARDS_TOOL,
    RAMSCH_PUSH_SKAT_TOOL,
    RAMSCH_DECLARE_GRAND_HAND_TOOL,
)


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


class AgentPushingTable(Table):
    """The agent opens a table whose Ramsch has pushing and holds seat 1, the middlehand; two people sit at 2 and 3."""

    def __init__(self, skat, agent, options=PUSHING):
        self.skat = skat
        self._commands = iter(range(1, 1000))
        agent_headers = agent.admitted()
        self.table_id = agent.open_table(options=options).json()["id"]
        people = [skat.member() for _ in range(3)]
        for seat, (headers, _) in zip((2, 3), people[:2], strict=True):
            skat.sit(headers, self.table_id, seat, command_id=f"command-sit-{seat}")
        with_known_deal(skat, self.table_id)
        self.with_deal(PLAIN_DEAL)
        self.at = {MIDDLEHAND: agent_headers, REARHAND: people[0][0], FOREHAND: people[1][0]}
        self.watcher = people[2][0]


class TestAnAgentAtATableWithPushing:
    def test_the_four_tools_are_offered_as_side_effecting_with_a_description_of_their_own(self, agent):
        agent.admitted()

        tools = {tool["name"]: tool for tool in agent.request("tools/list").json()["result"]["tools"]}

        assert all(name in tools for name in PUSHING_TOOLS)
        assert all("readOnlyHint" not in tools[name].get("annotations", {}) for name in PUSHING_TOOLS)
        assert len({tools[name]["description"] for name in PUSHING_TOOLS}) == len(PUSHING_TOOLS)
        assert "hand.pushing" in tools[RAMSCH_TAKE_SKAT_TOOL]["description"]

    def test_the_tool_that_opens_a_table_answers_the_pushing_rule(self, agent):
        agent.admitted()

        opened = agent.open_table(options=PUSHING)

        assert opened.json()["options"]["ramsch"]["pushing"] == {"rule": "jacks-stay", "grand_hand": "off"}

    def test_the_tool_that_opens_a_table_takes_a_grand_hand_the_stage_allows(self, agent):
        agent.admitted()

        opened = agent.open_table(options=GRAND_HAND_ALLOWED)

        assert opened.json()["options"]["ramsch"]["pushing"] == {"rule": "jacks-stay", "grand_hand": "allowed"}

    def test_declares_a_grand_hand_instead_of_the_ramsch_when_it_is_its_turn_and_plays_it(self, skat, agent):
        table = AgentPushingTable(skat, agent, GRAND_HAND_ALLOWED)
        assert not agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass").is_error
        table.passes(REARHAND)
        table.passes(FOREHAND)
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[FOREHAND])

        declared = agent.take_step(RAMSCH_DECLARE_GRAND_HAND_TOOL, table, command_id="agent-grand-hand")

        assert not declared.is_error, declared.text
        hand = json.loads(declared.text)["hand"]
        assert (hand["ramsch"], hand["pushing"], hand["declaring"]["declarer_seat"]) == (False, None, 1)
        for number, played in enumerate(PLAIN_HAND, 1):
            if table.holder_of(played) is MIDDLEHAND:
                assert not agent.play(table, played, command_id=f"agent-card-{number:02d}").is_error
            else:
                table.accepted(played)
        result = agent.read(table.table_id).json()["result"]
        assert (result["kind"], result["hand"], result["declarer_seat"]) == ("declared", True, 1)

    def test_a_table_that_does_not_allow_the_grand_hand_refuses_the_tool_as_wrong_phase(self, skat, agent):
        table = AgentPushingTable(skat, agent)
        assert not agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass").is_error
        table.passes(REARHAND)
        table.passes(FOREHAND)
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[FOREHAND])

        refused = agent.take_step(RAMSCH_DECLARE_GRAND_HAND_TOOL, table, command_id="agent-grand-hand")

        assert (refused.is_error, json.loads(refused.text)["reason"]) == (True, "wrong-phase")

    def test_takes_and_puts_back_the_skat_when_it_is_its_turn_and_plays_the_ramsch_on(self, skat, agent):
        table = AgentPushingTable(skat, agent)
        assert not agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass").is_error
        table.passes(REARHAND)
        table.passes(FOREHAND)
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[FOREHAND])

        taken = agent.take_step(RAMSCH_TAKE_SKAT_TOOL, table, command_id="agent-take")
        assert not taken.is_error, taken.text
        hand = json.loads(taken.text)["hand"]
        assert (len(hand["own_cards"]), hand["pushing"]["stage"]) == (12, "discarding")
        put = agent.take_step(
            RAMSCH_PUT_BACK_CARDS_TOOL,
            table,
            command_id="agent-put",
            cards=[card_body(each) for each in cards("DK DA")],
        )
        assert not put.is_error, put.text
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[REARHAND])

        assert agent.read(table.table_id).json()["hand"]["pushes"] == 2
        for number, played in enumerate(PLAIN_HAND, 1):
            if table.holder_of(played) is MIDDLEHAND:
                assert not agent.play(table, played, command_id=f"agent-card-{number:02d}").is_error
            else:
                table.accepted(played)
        result = agent.read(table.table_id).json()["result"]
        assert (result["pushes"], result["push_factor"]) == (2, 4)

    def test_a_refusal_is_a_failed_result_with_its_reason_and_spends_the_command_id(self, skat, agent):
        table = AgentPushingTable(skat, agent)
        assert not agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass").is_error
        table.passes(REARHAND)
        table.passes(FOREHAND)

        refused = agent.take_step(RAMSCH_PUSH_SKAT_TOOL, table, command_id="agent-push")
        again = agent.take_step(RAMSCH_PUSH_SKAT_TOOL, table, command_id="agent-push")

        assert (refused.is_error, json.loads(refused.text)["reason"]) == (True, "not-your-turn")
        assert (again.is_error, again.text) == (True, refused.text)
        assert table.record.progress.pushing == ()
