"""A send-away frees an agent's chair as it is and scores nothing; a person is refused."""

from dataclasses import replace

import pytest

from skat.table.records import HandProgress, Refusal, SendAway
from skat.table.send_away import decide_send_away, send_away_payload
from tests.support.open_chairs import PHASES, REARHAND, REARHAND_SEAT, account_of
from tests.support.played_game import after_the_first_game, table_in, with_agents


def agents_at_rearhand(table):
    return with_agents(table, REARHAND_SEAT)


class TestSendingAnAgentAway:
    @pytest.mark.parametrize("phase", PHASES)
    def test_frees_the_agents_chair_at_once_in_every_phase_of_a_hand(self, phase):
        table = agents_at_rearhand(PHASES[phase]())

        decision = decide_send_away(table, account_of(REARHAND))

        assert decision.refusal is None
        assert decision.table.chairs[REARHAND_SEAT - 1].occupant is None

    @pytest.mark.parametrize("phase", PHASES)
    def test_leaves_the_hand_its_steps_and_every_score_as_they_were_and_raises_the_version_once(self, phase):
        table = agents_at_rearhand(PHASES[phase]())

        freed = decide_send_away(table, account_of(REARHAND)).table

        assert freed == replace(table, version=table.version + 1, chairs=freed.chairs)
        assert [chair for chair in freed.chairs if chair.occupant is not None] == [
            chair for chair in table.chairs if chair.seat != REARHAND_SEAT
        ]

    def test_frees_the_chair_outside_a_hand_as_a_stand_up_does(self):
        between = agents_at_rearhand(after_the_first_game(table_in(HandProgress())))
        account = between.chairs[REARHAND_SEAT - 1].occupant.account_id

        decision = decide_send_away(between, account)

        assert decision.refusal is None
        assert decision.table.chairs[REARHAND_SEAT - 1].occupant is None
        assert not decision.table.chairs[REARHAND_SEAT - 1].ready
        assert decision.table.game_list == between.game_list

    def test_takes_the_ready_mark_with_the_chair(self):
        between = agents_at_rearhand(after_the_first_game(table_in(HandProgress()), REARHAND_SEAT))

        freed = decide_send_away(between, between.chairs[REARHAND_SEAT - 1].occupant.account_id).table

        assert not any(chair.ready for chair in freed.chairs if chair.seat == REARHAND_SEAT)


class TestRefusals:
    @pytest.mark.parametrize("phase", ["auction", "in-a-trick"])
    def test_a_person_cannot_be_sent_away(self, phase):
        table = PHASES[phase]()

        decision = decide_send_away(table, account_of(REARHAND))

        assert (decision.table, decision.refusal) == (table, Refusal.NOT_AN_AGENT)

    @pytest.mark.parametrize("account", ["account-nobody", "account-dora"])
    def test_an_account_without_a_chair_here_is_not_seated(self, account):
        table = agents_at_rearhand(PHASES["auction"]())

        decision = decide_send_away(table, account)

        assert (decision.table, decision.refusal) == (table, Refusal.NOT_SEATED)

    def test_a_chair_that_is_already_free_is_not_seated(self):
        freed = decide_send_away(agents_at_rearhand(PHASES["auction"]()), account_of(REARHAND)).table

        decision = decide_send_away(freed, account_of(REARHAND))

        assert (decision.table, decision.refusal) == (freed, Refusal.NOT_SEATED)


class TestThePayload:
    def test_names_the_table_and_the_agent_so_another_agent_is_another_request(self):
        first = send_away_payload(SendAway("command-1", "table-1", "account-a"))

        assert first != send_away_payload(SendAway("command-1", "table-1", "account-b"))
        assert first != send_away_payload(SendAway("command-1", "table-2", "account-a"))
