from dataclasses import replace

import pytest

from skat.engine.deal import Position, seats_from
from skat.table.records import Refusal, Series
from skat.web.mcp import CONTINUE_AFTER_RESULT_TOOL, START_NEW_SERIES_TOOL
from tests.support.payload_cards import DEALER_SEAT
from tests.web.support.agent import SUBJECT, Agent
from tests.web.support.series import play_the_dealt_series, tap_new_series
from tests.web.support.skat import AgentTable, Skat, stored, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


class TestStartNewSeries:
    @pytest.fixture
    def ended_series(self, skat, agent):
        """A series of three played to its end at a table where the agent holds the forehand chair."""
        table = AgentTable(skat, agent, FOREHAND)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 1))
        play_the_dealt_series(skat, table, 3)
        skat.client.cookies.clear()
        return table

    def start(self, agent, table, *, command_id="agent-new-series-0001"):
        return agent.call(START_NEW_SERIES_TOOL, table_id=table.table_id, command_id=command_id)

    def test_an_accepted_tap_marks_the_agents_chair_as_a_persons_tap_does(self, agent, ended_series):
        table = ended_series

        answer = self.start(agent, table)

        assert not answer.is_error, answer.text
        assert [chair["ready"] for chair in answer.json()["chairs"]] == [False, False, True]
        assert [chair.ready for chair in table.record.chairs] == [False, False, True]
        assert len(table.record.game_list) == 3

    def test_a_refused_tap_is_a_failed_result_with_the_reason_and_spends_the_id(self, skat, agent, ended_series):
        table = ended_series
        skat.stand(table.at[FOREHAND], table.table_id, command_id="agent-stands")
        before = stored(skat)

        refused = self.start(agent, table)
        unchanged = stored(skat)
        sat = skat.sit(table.at[FOREHAND], table.table_id, 3, command_id="agent-sits")
        again = self.start(agent, table)

        assert refused.is_error
        assert refused.json()["reason"] == Refusal.NOT_SEATED
        assert (again.is_error, again.text) == (refused.is_error, refused.text)
        assert unchanged[0] == before[0]
        assert sat.status_code == 200
        assert [chair.ready for chair in table.record.chairs] == [False, False, False]

    def test_the_same_call_again_answers_the_same_and_changes_nothing(self, agent, ended_series):
        table = ended_series
        first = self.start(agent, table)
        before = table.record

        again = self.start(agent, table)
        other_id = self.start(agent, table, command_id="agent-new-series-0002")

        assert (again.is_error, again.text) == (first.is_error, first.text)
        assert not other_id.is_error
        assert table.record == before

    def test_the_agents_tap_as_the_last_of_three_deletes_the_list_and_the_next_series_is_dealt(
        self, skat, agent, ended_series
    ):
        table = ended_series
        for number, position in enumerate((MIDDLEHAND, REARHAND), start=1):
            assert tap_new_series(skat, table.at[position], table.table_id, f"tap-new-{number}").status_code == 200
        assert len(table.record.game_list) == 3

        with streams_of(skat, table.table_id, [(table.at[position], None) for position in (MIDDLEHAND, REARHAND)]):
            assert not self.start(agent, table).is_error

        self.assert_next_series_dealt(agent, table)

    def test_three_agents_start_the_next_series_by_their_three_taps(self, skat, issuer, agent, ended_series):
        table = ended_series
        seats = seats_from(DEALER_SEAT)
        agents = [agent]
        for position in (MIDDLEHAND, REARHAND):
            other = Agent(skat, issuer, subject=f"{SUBJECT}-{position.name}")
            skat.stand(table.at[position], table.table_id, command_id=f"stand-{position.name}")
            skat.sit(other.admitted(), table.table_id, seats[position], command_id=f"sit-{position.name}")
            agents.append(other)
        skat.client.cookies.clear()

        answers = []
        for number, each in enumerate(agents):
            answers.append(self.start(each, table, command_id=f"agent-new-series-{number}"))
            if number == 1:
                assert len(table.record.game_list) == 3

        assert [answer.is_error for answer in answers] == [False] * 3
        self.assert_next_series_dealt(agent, table)

    def assert_next_series_dealt(self, agent, table):
        view = agent.read(table.table_id).json()
        assert view["series"] == {"game_number": 1, "game_count": 3, "over": False, "standings": None}
        assert view["hand"] is not None
        assert table.record.game_list == ()

    def test_the_description_says_the_third_tap_deletes_the_list_for_good(self, agent):
        tools = {tool["name"]: tool for tool in agent.request("tools/list").json()["result"]["tools"]}

        assert "for good" in tools[START_NEW_SERIES_TOOL]["description"]
        assert START_NEW_SERIES_TOOL in tools[CONTINUE_AFTER_RESULT_TOOL]["description"]
