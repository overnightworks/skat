"""An agent's owner sends his own agent away from the page, also outside the calling group; the chair keeps the owner
while the agent sits and loses it with the agent.
"""

import pytest

from skat.web.calling import CallRefusal
from tests.web.support.agent import Agent
from tests.web.support.calling import (
    CallingTable,
    call,
    listening,
    offer_of,
    only_row,
    person,
    read_control,
    send_away,
)
from tests.web.support.skat import streams_of

NOVA = "agent-nova"


def chair_two(skat, table_id):
    return skat.store.tables[table_id].chairs[1].occupant


@pytest.fixture
def owner(skat, issuer):
    """A person outside the calling group."""
    return person(skat, issuer, groups=())


@pytest.mark.usefixtures("watching")
class TestTheChairKeepsItsAgentsOwner(CallingTable):
    def test_an_agent_that_sits_down_by_itself_holds_its_chair_for_its_owner(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)

        assert chair_two(skat, table_id).owner_account == felix.id

    def test_an_agent_that_accepts_an_invitation_holds_its_chair_for_its_owner(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            call(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

            nova.accept(table_id, offer_of(nova))

        assert chair_two(skat, table_id).owner_account == felix.id

    def test_an_agent_that_opens_a_table_holds_its_chair_for_its_owner(self, skat, issuer, felix):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            table_id = nova.open_table().json()["id"]

            assert skat.store.tables[table_id].chairs[0].occupant.owner_account == felix.id

    def test_the_owner_goes_with_the_chair_when_the_agent_is_sent_away(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)

            send_away(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

        assert chair_two(skat, table_id) is None


class TestAnOwnerOutsideTheGroupSendsHisAgentAway(CallingTable):
    @pytest.fixture
    def seated(self, skat, issuer, felix, table_id, owner):
        """Nova, the agent of `owner`, sits in chair 2, and `owner` has a stream on the table."""
        nova = Agent(skat, issuer, NOVA, agent_owner=owner.id, agent_name="Nova")
        nova.sit_down(table_id, 2)
        with streams_of(skat, table_id, [(owner.headers, None)]):
            yield

    @pytest.mark.usefixtures("seated")
    def test_the_control_is_shown_with_the_row_here_and_the_send_away_opens_the_chair(self, skat, table_id, owner):

        control = read_control(skat, owner, table_id).json()
        (row,) = control["rows"]

        answer = send_away(skat, owner, table_id, row["key"])

        assert (control["shown"], row["name"], row["state"]) == (True, "Nova", "here")
        assert (answer.status_code, chair_two(skat, table_id)) == (200, None)

    @pytest.mark.usefixtures("seated")
    def test_the_answer_is_the_control_he_still_sees_without_the_agent(self, skat, table_id, owner):
        key = only_row(skat, owner, table_id)["key"]

        answer = send_away(skat, owner, table_id, key)

        assert answer.json() == {"shown": False, "rows": []}

    @pytest.mark.usefixtures("seated")
    def test_the_owner_retrying_the_same_command_id_is_answered_alike_and_changes_nothing_twice(
        self, skat, table_id, owner
    ):
        key = only_row(skat, owner, table_id)["key"]

        first = send_away(skat, owner, table_id, key, "command-owner-retry")
        after_first = skat.store.tables[table_id]
        second = send_away(skat, owner, table_id, key, "command-owner-retry")

        assert (second.status_code, second.json()) == (first.status_code, first.json())
        assert skat.store.tables[table_id] == after_first

    @pytest.mark.usefixtures("seated")
    def test_the_right_needs_no_group_read_so_an_issuer_that_refuses_it_changes_nothing(
        self, skat, issuer, table_id, owner
    ):
        key = only_row(skat, owner, table_id)["key"]
        issuer.refuses_refresh_grants = True

        answer = send_away(skat, owner, table_id, key)

        assert (answer.status_code, chair_two(skat, table_id)) == (200, None)

    @pytest.mark.usefixtures("seated")
    def test_another_person_outside_the_group_sees_nothing_and_is_refused_not_allowed(
        self, skat, issuer, table_id, owner
    ):
        key = only_row(skat, owner, table_id)["key"]
        stranger = person(skat, issuer, groups=())

        with streams_of(skat, table_id, [(stranger.headers, None)]):
            control = read_control(skat, stranger, table_id).json()
            answer = send_away(skat, stranger, table_id, key)

        assert control == {"shown": False, "rows": []}
        assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
        assert chair_two(skat, table_id).display_name == "Nova"


class TestAnOwnerSeatedWithoutAStreamIsAtTheTable(CallingTable):
    def test_the_control_shows_the_row_here_and_the_send_away_opens_the_chair(self, skat, issuer, table_id, owner):
        Agent(skat, issuer, NOVA, agent_owner=owner.id, agent_name="Nova").sit_down(table_id, 2)
        skat.sit(owner.headers, table_id, 3, command_id="command-owner-sits")
        skat.client.cookies.clear()

        control = read_control(skat, owner, table_id).json()
        (row,) = control["rows"]
        answer = send_away(skat, owner, table_id, row["key"])

        assert (control["shown"], row["state"]) == (True, "here")
        assert (answer.status_code, chair_two(skat, table_id)) == (200, None)
