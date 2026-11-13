"""A send-away frees an agent's chair as it is and scores nothing; a person is refused."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skat.table.records import Actor, HandProgress, Refusal, SeatHeld, SendAway
from skat.table.send_away import decide_send_away, decide_send_away_by, send_away_payload
from tests.support.open_chairs import PHASES, REARHAND, REARHAND_SEAT, account_of
from tests.support.played_game import after_the_first_game, table_in, with_agents

NOW = datetime(2026, 11, 12, 9, tzinfo=UTC)
OWNER = "account-owner"
SENDER = "account-sender"


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

        left_marks = replace(freed.progress, seats_held=frozenset(), former_holders=frozenset())
        assert replace(freed, progress=left_marks) == replace(table, version=table.version + 1, chairs=freed.chairs)
        assert [chair for chair in freed.chairs if chair.occupant is not None] == [
            chair for chair in table.chairs if chair.seat != REARHAND_SEAT
        ]

    @pytest.mark.parametrize("phase", PHASES)
    def test_marks_the_sent_away_agent_as_the_holder_of_its_seat_in_the_hand(self, phase):
        table = agents_at_rearhand(PHASES[phase]())

        freed = decide_send_away(table, account_of(REARHAND)).table

        assert freed.progress.seats_held == {SeatHeld(account_of(REARHAND), REARHAND_SEAT)}

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


class TestWhoMaySendAnAgentAway:
    def table(self):
        return with_agents(PHASES["auction"](), REARHAND_SEAT, owner_account=OWNER)

    def sent_by(self, table, sender, *, is_member=True, present=True, agent=None):
        command = SendAway("command-away", table.id.value, agent or account_of(REARHAND))
        connected = frozenset({sender}) if present else frozenset()
        return decide_send_away_by(table, command, Actor(sender, "Sender"), connected, is_member, NOW)

    @pytest.mark.parametrize("sender", [SENDER, OWNER])
    def test_a_member_and_the_owner_present_free_the_chair(self, sender):
        decision = self.sent_by(self.table(), sender)

        assert decision.refusal is None
        assert decision.table.chairs[REARHAND_SEAT - 1].occupant is None

    def test_the_owner_outside_the_group_frees_the_chair(self):
        decision = self.sent_by(self.table(), OWNER, is_member=False)

        assert decision.refusal is None
        assert decision.table.chairs[REARHAND_SEAT - 1].occupant is None

    @pytest.mark.parametrize(
        ("sender", "changes"),
        [
            pytest.param(SENDER, {"is_member": False}, id="a-person-who-is-no-member-and-no-owner"),
            pytest.param(SENDER, {"present": False}, id="a-member-who-is-not-at-the-table"),
            pytest.param(OWNER, {"is_member": False, "present": False}, id="the-owner-who-is-not-at-the-table"),
        ],
    )
    def test_nobody_else_may_and_the_chair_stays(self, sender, changes):
        table = self.table()

        decision = self.sent_by(table, sender, **changes)

        assert (decision.table, decision.refusal) == (table, Refusal.NOT_ALLOWED)

    def test_a_member_is_refused_by_the_chairs_own_reason_when_no_agent_sits_there(self):
        table = PHASES["auction"]()

        assert self.sent_by(table, SENDER).refusal is Refusal.NOT_AN_AGENT
        assert self.sent_by(table, SENDER, agent="account-nobody").refusal is Refusal.NOT_SEATED


class TestThePayload:
    def test_names_the_table_and_the_agent_so_another_agent_is_another_request(self):
        first = send_away_payload(SendAway("command-1", "table-1", "account-a"))

        assert first != send_away_payload(SendAway("command-1", "table-1", "account-b"))
        assert first != send_away_payload(SendAway("command-1", "table-2", "account-a"))
