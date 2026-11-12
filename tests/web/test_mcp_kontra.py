"""An agent opponent says its Kontra word, or answers that it says none, through the tools of /mcp."""

from dataclasses import replace

import pytest

from skat.engine.deal import Position
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraRefusal, KontraSayer
from skat.table.records import TableOptions
from skat.web.mcp import SAY_KONTRA_TOOL, SAY_NO_WORD_TOOL
from tests.web.support.skat import AgentTable, Skat, stored

FOREHAND = Position.FOREHAND


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def kontra_table(skat, agent):
    """A Hand game declared at a table with Kontra and Re where the agent holds the forehand, whose turn it is."""
    table = AgentTable(skat, agent, FOREHAND)
    table.declared_hand_game()
    options = KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD)
    skat.store.tables[table.table_id] = replace(table.record, options=TableOptions(kontra=options))
    skat.client.cookies.clear()
    return table


class TestSayKontra:
    def say(self, agent, table, word="kontra", *, command_id="agent-word-0001", **changes):
        return agent.take_step(SAY_KONTRA_TOOL, table, command_id=command_id, word=word, **changes)

    def test_an_agent_opponent_says_kontra_as_a_person_does_under_its_own_account(self, agent, kontra_table):
        assert agent.read(kontra_table.table_id).json()["hand"]["playing"]["kontra"]["my_word"] == "kontra"

        answer = self.say(agent, kontra_table)

        assert not answer.is_error, answer.text
        kontra = answer.json()["hand"]["playing"]["kontra"]
        assert kontra == {
            "said": [{"seat": 3, "word": "kontra"}],
            "factor": 2,
            "my_word": None,
            "my_word_answered": False,
        }
        assert agent.read(kontra_table.table_id).json() == answer.json()
        assert kontra_table.record.progress.words[0].position is FOREHAND

    def test_a_refused_word_is_a_failed_result_with_the_reason_and_spends_the_id(self, agent, kontra_table):
        before = stored(kontra_table.skat)

        answer = self.say(agent, kontra_table, "re")

        assert answer.is_error
        assert answer.json()["reason"] == KontraRefusal.NOT_YOUR_WORD
        assert stored(kontra_table.skat)[0] == before[0]
        assert "reused" in self.say(agent, kontra_table, "kontra", version=0).text


class TestSayNoWord:
    def say_no_word(self, agent, table, *, command_id="agent-no-word-0001", **changes):
        return agent.call(
            SAY_NO_WORD_TOOL,
            table_id=table.table_id,
            command_id=command_id,
            **{"version": table.record.version, **changes},
        )

    def test_an_agent_opponent_answers_no_word_and_the_word_stays_open_under_its_own_account(self, agent, kontra_table):
        answer = self.say_no_word(agent, kontra_table)

        assert not answer.is_error, answer.text
        kontra = answer.json()["hand"]["playing"]["kontra"]
        assert (kontra["my_word"], kontra["my_word_answered"], kontra["said"]) == ("kontra", True, [])
        assert agent.read(kontra_table.table_id).json() == answer.json()
        assert [each.position for each in kontra_table.record.progress.no_words] == [FOREHAND]
