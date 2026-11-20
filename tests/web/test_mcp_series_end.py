import pytest

from skat.engine.deal import Position
from skat.host.app import ServerRounds
from skat.table.records import Refusal
from skat.table.series_end import END_ANSWER_SECONDS
from skat.web.mcp import AGREE_TO_END_SERIES_TOOL, GIVE_UP_GAME_TOOL, REFUSE_TO_END_SERIES_TOOL
from skat.web.tables import TABLES_PATH
from tests.web.support.skat import AgentTable, Skat


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


def test_the_series_of_a_table_reads_at_the_tool_as_the_route_gives_it(skat, agent):
    headers = agent.admitted()
    table_id = skat.create(headers, series_length=12).json()["id"]

    view = agent.read(table_id).json()

    assert view["series"] == {
        "number": 1,
        "game_number": 0,
        "game_count": 12,
        "over": False,
        "standings": None,
        "end_proposal": None,
        "end_refused_seats": [],
        "new_series_answer_by": None,
    }
    assert view == skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()


class TestEndingTheSeriesEarly:
    @pytest.fixture
    def between_games(self, skat, agent):
        """The agent opened the table at seat 1 and gave up its first game: a result stands, no hand runs."""
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        agent.call(
            GIVE_UP_GAME_TOOL, table_id=table.table_id, command_id="agent-give-up-0001", version=table.record.version
        )
        return table

    def test_an_agent_proposes_the_end_under_its_own_seat_and_takes_it_back(self, agent, between_games):
        proposed = agent.call(AGREE_TO_END_SERIES_TOOL, table_id=between_games.table_id, command_id="agent-agree-0001")

        assert not proposed.is_error, proposed.text
        proposal = agent.read(between_games.table_id).json()["series"]["end_proposal"]
        assert (proposal["proposer_seat"], proposal["agreed_seats"]) == (1, [1])

        refused = agent.call(REFUSE_TO_END_SERIES_TOOL, table_id=between_games.table_id, command_id="agent-refuse-0001")

        assert not refused.is_error, refused.text
        assert agent.read(between_games.table_id).json()["series"]["end_proposal"] is None

    def test_a_refused_call_is_a_failed_result_with_the_reason_and_spends_the_id(self, agent, between_games):
        answer = agent.call(REFUSE_TO_END_SERIES_TOOL, table_id=between_games.table_id, command_id="agent-refuse-0001")

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.NO_PROPOSAL
        again = agent.call(AGREE_TO_END_SERIES_TOOL, table_id=between_games.table_id, command_id="agent-refuse-0001")
        assert "reused" in again.text


class TestTheMinuteOfAnAgentsProposal:
    @pytest.fixture
    def skat(self, hold, issuer, time):
        skat = Skat(
            lambda: hold,
            issuer_transports=issuer.transports,
            now=time.moment,
            chair_clock=time.clock,
            chair_scheduler=time,
            rounds=ServerRounds(end_answer_recovery_seconds=END_ANSWER_SECONDS * 100),
        )
        with skat.client:
            yield skat

    def test_a_yes_through_the_tool_ends_the_proposal_a_minute_later_and_names_the_silent_seats(
        self, skat, agent, time
    ):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        agent.call(
            GIVE_UP_GAME_TOOL, table_id=table.table_id, command_id="agent-give-up-0001", version=table.record.version
        )
        proposed = agent.call(AGREE_TO_END_SERIES_TOOL, table_id=table.table_id, command_id="agent-agree-0001")
        assert not proposed.is_error, proposed.text

        skat.client.portal.call(time.advance, END_ANSWER_SECONDS)

        series = agent.read(table.table_id).json()["series"]
        assert (series["end_proposal"], series["end_refused_seats"]) == (None, [2, 3])
