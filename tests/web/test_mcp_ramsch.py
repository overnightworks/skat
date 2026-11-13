import json

import pytest

from skat.web.mcp import AUCTION_PASS_TOOL, CONTINUE_AFTER_RESULT_TOOL, OPEN_TABLE_TOOL
from tests.support.payload_cards import with_known_deal
from tests.web.support.playing import FOREHAND, MIDDLEHAND, PLAIN_DEAL, PLAIN_HAND, REARHAND, Table
from tests.web.support.skat import Skat

RAMSCH = {
    "ramsch": {"occasion": "passed-in", "scoring": "points", "jungfrau": "doubles-loser", "durchmarsch": "wins-120"}
}


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


class AgentRamschTable(Table):
    """The agent opens a Ramsch table and holds seat 1, the middlehand; two people sit at seats 2 and 3."""

    def __init__(self, skat, agent):
        self.skat = skat
        self._commands = iter(range(1, 1000))
        agent_headers = agent.admitted()
        self.table_id = agent.open_table(options=RAMSCH).json()["id"]
        people = [skat.member() for _ in range(3)]
        for seat, (headers, _) in zip((2, 3), people[:2], strict=True):
            skat.sit(headers, self.table_id, seat, command_id=f"command-sit-{seat}")
        with_known_deal(skat, self.table_id)
        self.with_deal(PLAIN_DEAL)
        self.at = {MIDDLEHAND: agent_headers, REARHAND: people[0][0], FOREHAND: people[1][0]}
        self.watcher = people[2][0]


class TestAnAgentAtARamschTable:
    def test_the_tool_that_opens_a_table_takes_the_ramsch_options_and_answers_them(self, skat, agent):
        agent.admitted()
        tools = {tool["name"]: tool for tool in agent.request("tools/list").json()["result"]["tools"]}

        opened = agent.open_table(options=RAMSCH)

        assert "ramsch" in json.dumps(tools[OPEN_TABLE_TOOL]["inputSchema"])
        assert opened.json()["options"]["ramsch"] == {**RAMSCH["ramsch"], "pushing": None}

    def test_plays_a_whole_ramsch_with_play_card_and_continues_after_its_result(self, skat, agent):
        table = AgentRamschTable(skat, agent)
        assert not agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass").is_error
        table.passes(REARHAND)
        table.passes(FOREHAND)

        for number, played in enumerate(PLAIN_HAND, 1):
            if table.holder_of(played) is MIDDLEHAND:
                assert not agent.play(table, played, command_id=f"agent-card-{number:02d}").is_error
            else:
                table.accepted(played)

        result = agent.read(table.table_id).json()["result"]
        assert result == table.result()
        assert (result["kind"], result["ordinal"]) == ("ramsch", 1)
        tapped = agent.call(
            CONTINUE_AFTER_RESULT_TOOL,
            table_id=table.table_id,
            command_id="agent-tap",
            ordinal=result["ordinal"],
            series=1,
        )
        assert not tapped.is_error
        assert [chair["ready"] for chair in agent.read(table.table_id).json()["chairs"]] == [True, False, False]
