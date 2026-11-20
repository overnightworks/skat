from dataclasses import replace

import pytest

from skat.engine.deal import Position, seats_from
from skat.table.records import EndReason, Refusal, Series
from skat.web.mcp import (
    CHANGE_NEXT_SERIES_SETTINGS_TOOL,
    CONTINUE_AFTER_RESULT_TOOL,
    START_NEW_SERIES_TOOL,
    STOP_PLAYING_TOOL,
)
from tests.support.payload_cards import DEALER_SEAT
from tests.web.support.agent import SUBJECT, Agent
from tests.web.support.series import change_next_settings, play_the_dealt_series, tap_new_series
from tests.web.support.skat import AgentTable, Skat, stored, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


def start_new_series(agent, table, *, command_id="agent-new-series-0001", series=1, settings=0):
    return agent.call(
        START_NEW_SERIES_TOOL, table_id=table.table_id, command_id=command_id, series=series, settings=settings
    )


class TestStartNewSeries:
    @pytest.fixture
    def ended_series(self, skat, agent):
        """A series of three played to its end at a table where the agent holds the forehand chair."""
        table = AgentTable(skat, agent, FOREHAND)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 1))
        play_the_dealt_series(skat, table, 3)
        skat.client.cookies.clear()
        return table

    def start(self, agent, table, **more):
        return start_new_series(agent, table, **more)

    def test_an_accepted_tap_marks_the_agents_chair_as_a_persons_tap_does(self, agent, ended_series):
        table = ended_series

        answer = self.start(agent, table)

        assert not answer.is_error, answer.text
        assert [chair["ready"] for chair in agent.read(table.table_id).json()["chairs"]] == [False, False, True]
        assert [chair.ready for chair in table.record.chairs] == [False, False, True]
        assert len(table.record.game_list) == 3

    def test_a_refused_tap_is_a_failed_result_with_the_reason_and_spends_the_id(self, skat, agent, ended_series):
        table = ended_series
        skat.stand(table.at[FOREHAND], table.table_id, command_id="agent-stands")
        before = stored(skat)

        every_tool = agent.offered_every_tool()
        refused = self.start(every_tool, table)
        unchanged = stored(skat)
        sat = skat.sit(table.at[FOREHAND], table.table_id, 3, command_id="agent-sits")
        again = self.start(every_tool, table)

        assert refused.is_error
        assert refused.json()["reason"] == Refusal.NOT_SEATED
        assert (again.is_error, again.text) == (refused.is_error, refused.text)
        assert unchanged[0] == before[0]
        assert sat.status_code == 200
        assert [chair.ready for chair in table.record.chairs] == [False, False, False]

    @pytest.mark.parametrize("series", [2, 3], ids=["a-series-not-yet-started", "a-series-further-on"])
    def test_a_call_naming_another_series_is_a_failed_result_and_changes_nothing(self, agent, ended_series, series):
        table = ended_series
        before = table.record

        refused = self.start(agent, table, series=series)

        assert refused.is_error
        assert refused.json()["reason"] == Refusal.STALE_SERIES
        assert table.record == before
        assert not self.start(agent, table, command_id="agent-new-series-0002").is_error

    def test_a_call_naming_no_series_is_refused_before_it_acts(self, agent, ended_series):
        table = ended_series
        before = table.record

        refused = agent.call(START_NEW_SERIES_TOOL, table_id=table.table_id, command_id="agent-no-series", settings=0)

        assert refused.is_error
        assert table.record == before

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
        assert view["series"] == {
            "number": 2,
            "game_number": 1,
            "game_count": 3,
            "over": False,
            "standings": None,
            "end_proposal": None,
            "end_refused_seats": [],
            "new_series_answer_by": None,
            "next_settings": None,
        }
        assert view["hand"] is not None
        assert table.record.game_list == ()

    def test_the_input_schema_offers_the_settings_the_tap_answers_and_requires_them_not(self, agent):
        listed = agent.offered_every_tool().request("tools/list")
        tools = {each["name"]: each for each in listed.json()["result"]["tools"]}

        schema = tools[START_NEW_SERIES_TOOL]["inputSchema"]

        assert ("settings" in schema["properties"], "settings" in schema["required"]) == (True, False)

    @pytest.mark.parametrize("tool", [CONTINUE_AFTER_RESULT_TOOL, START_NEW_SERIES_TOOL])
    def test_the_input_schema_requires_the_series_the_tap_answers(self, agent, tool):
        listed = agent.offered_every_tool().request("tools/list")
        tools = {each["name"]: each for each in listed.json()["result"]["tools"]}

        schema = tools[tool]["inputSchema"]

        assert "series" in schema["properties"]
        assert "series" in schema["required"]

    def test_the_description_says_the_finished_games_stay_stored(self, agent):
        listed = agent.offered_every_tool().request("tools/list")
        tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}

        assert "stay stored" in tools[START_NEW_SERIES_TOOL]["description"]
        assert START_NEW_SERIES_TOOL in tools[CONTINUE_AFTER_RESULT_TOOL]["description"]

    def test_the_agent_is_offered_both_answers_at_the_series_end(self, agent, ended_series):
        offered = agent.listed_tools()

        assert {START_NEW_SERIES_TOOL, STOP_PLAYING_TOOL} <= set(offered)

    def test_the_agents_stop_ends_the_table_as_a_persons_aufhoeren_does(self, agent, ended_series):
        table = ended_series

        answer = agent.call(STOP_PLAYING_TOOL, table_id=table.table_id, command_id="agent-stops")

        assert not answer.is_error, answer.text
        assert agent.read(table.table_id).json()["ended"]["reason"] == EndReason.CLOSED

    def test_the_descriptions_name_the_minute_after_which_a_silent_seat_ends_the_table(self, agent):
        listed = agent.offered_every_tool().request("tools/list")
        tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}

        assert STOP_PLAYING_TOOL in tools[START_NEW_SERIES_TOOL]["description"]
        for tool in (START_NEW_SERIES_TOOL, STOP_PLAYING_TOOL):
            assert "series.new_series_answer_by" in tools[tool]["description"]


class TestChangeNextSeriesSettings:
    @pytest.fixture
    def ended_series(self, skat, agent):
        """A series of three played to its end at a table where the agent holds the forehand chair."""
        table = AgentTable(skat, agent, FOREHAND)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 1))
        play_the_dealt_series(skat, table, 3)
        skat.client.cookies.clear()
        return table

    def save(self, agent, table, *, command_id="agent-settings-0001", series_length=12, **more):
        return agent.call(
            CHANGE_NEXT_SERIES_SETTINGS_TOOL,
            table_id=table.table_id,
            command_id=command_id,
            series=1,
            series_length=series_length,
            **more,
        )

    def test_the_agents_save_on_older_settings_is_a_failed_result_naming_the_reason(self, skat, agent, ended_series):
        table = ended_series
        change_next_settings(skat, table.at[MIDDLEHAND], table.table_id, "save-first", series_length=12)

        refused = self.save(agent, table, series_length=15)

        assert (refused.is_error, refused.json()["reason"]) == (True, Refusal.STALE_SETTINGS)
        assert agent.read(table.table_id).json()["series"]["next_settings"]["game_count"] == 12

    def test_the_agent_saves_the_next_series_settings_as_a_person_does(self, agent, ended_series):
        table = ended_series

        answer = self.save(agent, table, options={"show_running_points": True})

        assert not answer.is_error, answer.text
        line = agent.read(table.table_id).json()["series"]["next_settings"]
        assert (line["game_count"], line["revision"], line["options"]["show_running_points"]) == (12, 1, True)

    def test_the_agents_save_takes_back_the_marks_of_the_people(self, skat, agent, ended_series):
        table = ended_series
        assert tap_new_series(skat, table.at[MIDDLEHAND], table.table_id, "tap-new-1").status_code == 200

        assert not self.save(agent, table).is_error

        assert [chair.ready for chair in table.record.chairs] == [False, False, False]

    def test_a_save_by_a_person_takes_back_the_agents_new_series(self, skat, agent, ended_series):
        table = ended_series
        assert not start_new_series(agent, table).is_error
        assert table.record.chairs[2].ready

        saved = change_next_settings(skat, table.at[MIDDLEHAND], table.table_id, "save-first", series_length=12)

        assert saved.status_code == 200
        assert [chair["ready"] for chair in agent.read(table.table_id).json()["chairs"]] == [False, False, False]

    def test_the_agents_tap_on_older_settings_is_a_failed_result_naming_the_reason(self, skat, agent, ended_series):
        table = ended_series
        change_next_settings(skat, table.at[MIDDLEHAND], table.table_id, "save-first", series_length=12)

        refused = start_new_series(agent, table, settings=0)

        assert (refused.is_error, refused.json()["reason"]) == (True, Refusal.STALE_SETTINGS)

    def test_the_agent_is_offered_the_change_at_the_series_end(self, agent, ended_series):
        assert CHANGE_NEXT_SERIES_SETTINGS_TOOL in agent.listed_tools()

    def test_the_description_names_the_settings_the_sheet_shows_and_what_a_save_takes_back(self, agent):
        listed = agent.offered_every_tool().request("tools/list")
        tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}

        description = tools[CHANGE_NEXT_SERIES_SETTINGS_TOOL]["description"]

        assert all(word in description for word in ("series_length", "options", "series.next_settings", "„Neue Serie“"))
