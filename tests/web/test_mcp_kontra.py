"""An agent opponent says its Kontra word, or answers that it says none, through the tools of /mcp."""

import pytest

from skat.engine.deal import Position
from skat.engine.kontra import KontraRefusal, Word
from skat.table.records import NoWordSaid, Refusal
from skat.web.kontra import TABLE_KONTRA_SUFFIX, TABLE_NO_WORD_SUFFIX
from skat.web.mcp import SAY_KONTRA_TOOL, SAY_NO_WORD_TOOL
from tests.web.support.playing import HERZ_GAME, Table, contested_auction
from tests.web.support.skat import AgentTable, Skat, stored

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


def kontra_options(deadline, sayer="any-opponent"):
    return {"kontra": {"sayer": sayer, "reach": "kontra-re", "deadline": deadline}}


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def kontra_table(skat, agent):
    """A Hand game declared at a table opened with Kontra and Re, the agent holding the forehand and the turn."""
    table = AgentTable(skat, agent, FOREHAND, options=kontra_options("own-card"))
    table.declared_hand_game()
    skat.client.cookies.clear()
    return table


class TestSayKontra:
    def say(self, agent, table, word="kontra", *, command_id="agent-word-0001", **changes):
        return agent.take_step(SAY_KONTRA_TOOL, table, command_id=command_id, word=word, **changes)

    def test_an_agent_opponent_says_kontra_as_a_person_does_under_its_own_account(self, agent, kontra_table):
        assert agent.read(kontra_table.table_id).json()["hand"]["playing"]["kontra"]["my_word"] == "kontra"

        answer = self.say(agent, kontra_table)

        assert not answer.is_error, answer.text
        assert agent.read(kontra_table.table_id).json()["hand"]["playing"]["kontra"] == {
            "said": [{"seat": 3, "word": "kontra"}],
            "factor": 2,
            "my_word": None,
            "my_word_answered": False,
            "first_card_waits_on": [],
            "first_card_declined": [],
        }
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
        kontra = agent.read(kontra_table.table_id).json()["hand"]["playing"]["kontra"]
        assert (kontra["my_word"], kontra["my_word_answered"], kontra["said"]) == ("kontra", True, [])
        assert [each.position for each in kontra_table.record.progress.no_words] == [FOREHAND]


class TestAFirstCardTable:
    """A table opened through the tools with the first-card deadline: the first card waits for each word or decline."""

    def first_card_table(self, skat, agent, position, sayer="any-opponent"):
        table = AgentTable(skat, agent, position, options=kontra_options("first-card", sayer))
        skat.client.cookies.clear()
        return table

    def waits(self, agent, table):
        return agent.read(table.table_id).json()["hand"]["playing"]["kontra"]["first_card_waits_on"]

    def person_answers_no_word(self, table, position):
        answer = table.act(TABLE_NO_WORD_SUFFIX, table.at[position])
        assert answer.status_code == 200, answer.text

    def test_an_agent_opens_the_table_with_the_first_card_deadline_and_reads_it_back(self, skat, agent):
        table = self.first_card_table(skat, agent, MIDDLEHAND)

        assert agent.read(table.table_id).json()["options"]["kontra"]["deadline"] == "first-card"

    def test_the_agents_first_card_is_refused_until_each_opponent_has_answered_and_then_played(self, skat, agent):
        table = self.first_card_table(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        waiting = agent.play(table, HERZ_GAME[0], command_id="agent-move-0001")
        agent.take_step(SAY_NO_WORD_TOOL, table, command_id="agent-no-word-0001")
        one_opponent_answered = agent.play(table, HERZ_GAME[0], command_id="agent-move-0002")
        self.person_answers_no_word(table, REARHAND)
        answered = agent.play(table, HERZ_GAME[0], command_id="agent-move-0003")

        assert [each.json()["reason"] for each in (waiting, one_opponent_answered)] == [KontraRefusal.WORDS_DUE] * 2
        assert not answered.is_error, answered.text
        assert table.record.progress.plays != ()

    @pytest.mark.parametrize(
        ("tool", "answer"),
        [
            pytest.param(SAY_KONTRA_TOOL, {"word": "re"}, id="re"),
            pytest.param(SAY_NO_WORD_TOOL, {}, id="no-word"),
        ],
    )
    def test_the_declarers_answer_to_a_kontra_frees_the_first_card_without_the_other_opponent_answering(
        self, skat, agent, tool, answer
    ):
        table = self.first_card_table(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        said = table.act(TABLE_KONTRA_SUFFIX, table.at[FOREHAND], body={"word": "kontra"})
        assert said.status_code == 200, said.text
        table.refused(table.at[FOREHAND], HERZ_GAME[0], KontraRefusal.WORDS_DUE)
        assert self.waits(agent, table)

        answered = agent.take_step(tool, table, command_id="agent-answer-0001", **answer)

        assert not answered.is_error, answered.text
        assert not self.waits(agent, table)
        table.accepted(HERZ_GAME[0])

    def test_where_only_bidders_say_kontra_a_bidding_agent_answering_no_word_frees_the_first_card(self, skat, agent):
        table = self.first_card_table(skat, agent, FOREHAND, "bidders-only")
        contested_auction(table)
        skat.client.cookies.clear()

        waiting = agent.play(table, HERZ_GAME[0], command_id="agent-move-0001")
        agent.take_step(SAY_NO_WORD_TOOL, table, command_id="agent-no-word-0001")
        answered = agent.play(table, HERZ_GAME[0], command_id="agent-move-0002")

        assert waiting.json()["reason"] == KontraRefusal.WORDS_DUE
        assert not answered.is_error, answered.text

    def test_where_only_bidders_say_kontra_an_agent_that_did_not_bid_is_refused_its_no_word(self, skat, agent):
        table = self.first_card_table(skat, agent, REARHAND, "bidders-only")
        contested_auction(table)
        skat.client.cookies.clear()
        before = stored(skat)

        refused = agent.take_step(SAY_NO_WORD_TOOL, table, command_id="agent-no-word-0001")

        assert refused.is_error
        assert refused.json()["reason"] == KontraRefusal.DID_NOT_BID
        assert stored(skat)[0] == before[0]

    def test_an_agent_opponents_no_word_is_a_decline_that_ends_its_wait_for_good(self, skat, agent):
        table = self.first_card_table(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        assert agent.read(table.table_id).json()["hand"]["playing"]["kontra"]["my_word"] == "kontra"

        answered = agent.take_step(SAY_NO_WORD_TOOL, table, command_id="agent-no-word-0001")
        again = agent.take_step(SAY_NO_WORD_TOOL, table, command_id="agent-no-word-0002")
        late_kontra = self.say_kontra(agent, table)

        kontra = agent.read(table.table_id).json()["hand"]["playing"]["kontra"]
        assert not answered.is_error, answered.text
        assert not again.is_error, again.text
        assert late_kontra.json()["reason"] == KontraRefusal.NOT_YOUR_WORD
        assert (kontra["my_word"], bool(kontra["first_card_waits_on"])) == (None, True)
        assert table.record.progress.no_words == {NoWordSaid(FOREHAND, Word.KONTRA)}

    @pytest.mark.parametrize("declarer_answer", ["re", "no-word"])
    def test_the_agents_first_card_waits_for_the_declarers_answer_to_the_kontra_it_said(
        self, skat, agent, declarer_answer
    ):
        table = self.first_card_table(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        self.person_answers_no_word(table, REARHAND)
        said = self.say_kontra(agent, table)

        waiting = agent.play(table, HERZ_GAME[0], command_id="agent-move-0001")
        if declarer_answer == "re":
            answered = table.act(TABLE_KONTRA_SUFFIX, table.at[MIDDLEHAND], body={"word": "re"})
            assert answered.status_code == 200, answered.text
        else:
            self.person_answers_no_word(table, MIDDLEHAND)
        answered_play = agent.play(table, HERZ_GAME[0], command_id="agent-move-0002")

        assert not said.is_error, said.text
        assert waiting.json()["reason"] == KontraRefusal.WORDS_DUE
        assert not answered_play.is_error, answered_play.text
        assert table.record.progress.plays != ()

    @pytest.mark.parametrize(
        ("tool", "changes"),
        [
            pytest.param(SAY_KONTRA_TOOL, {"word": "kontra"}, id="kontra"),
            pytest.param(SAY_NO_WORD_TOOL, {}, id="no-word"),
        ],
    )
    def test_a_stale_version_is_refused_and_leaves_the_waiting_table_unchanged(self, skat, agent, tool, changes):
        table = self.first_card_table(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        before = stored(skat)

        refused = agent.take_step(tool, table, command_id="agent-stale-0001", **{**changes, "version": 0})

        assert refused.is_error
        assert refused.json()["reason"] == Refusal.STALE_VERSION
        assert stored(skat)[0] == before[0]

    @pytest.mark.parametrize(
        ("tool", "changes"),
        [
            pytest.param(SAY_KONTRA_TOOL, {"word": "kontra"}, id="kontra"),
            pytest.param(SAY_NO_WORD_TOOL, {}, id="no-word"),
        ],
    )
    def test_an_agent_that_watches_the_first_card_table_is_refused_its_word(self, skat, agent, tool, changes):
        agent.admitted()
        table = Table(skat, options=kontra_options("first-card"))
        table.declared_hand_game()
        skat.client.cookies.clear()
        before = stored(skat)

        refused = agent.offered_every_tool().take_step(tool, table, command_id="agent-watch-0001", **changes)

        assert refused.is_error
        assert refused.json()["reason"] == Refusal.NOT_SEATED
        assert stored(skat)[0] == before[0]

    def test_an_agent_opponent_that_answers_after_the_first_card_is_refused_as_too_late(self, skat, agent):
        table = self.first_card_table(skat, agent, REARHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        said = table.act(TABLE_KONTRA_SUFFIX, table.at[FOREHAND], body={"word": "kontra"})
        assert said.status_code == 200, said.text
        self.person_answers_no_word(table, MIDDLEHAND)
        table.accepted(HERZ_GAME[0])
        before = stored(skat)

        refused = agent.take_step(SAY_NO_WORD_TOOL, table, command_id="agent-late-0001")

        assert refused.is_error
        assert refused.json()["reason"] == KontraRefusal.TOO_LATE
        assert stored(skat)[0] == before[0]

    def say_kontra(self, agent, table):
        return agent.take_step(SAY_KONTRA_TOOL, table, command_id="agent-word-0001", word="kontra")
