"""The seated players vote to abort a hand with an open chair through the routes and the tools of an agent."""

import pytest

from skat.table.records import Actor, SendAway
from skat.web.abort import TABLE_ABORT_AGREE_SUFFIX, TABLE_ABORT_REFUSE_SUFFIX
from skat.web.mcp import AGREE_TO_ABORT_HAND_TOOL, REFUSE_TO_ABORT_HAND_TOOL
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import Skat
from tests.web.support.waiting_table import WaitingTable


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def waiting(skat, issuer):
    """The agent in seat 1 and the person in seat 3 sit at a hand that waits for seat 2."""
    table = WaitingTable(skat, issuer)
    table.send_the_second_agent_away()
    return table


def vote(table, suffix, command_id, headers=None):
    table.skat.client.cookies.clear()
    return table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{suffix}",
        json={"command_id": command_id},
        headers={"origin": TEST_PUBLIC_ORIGIN, **(table.person_headers if headers is None else headers)},
    )


def the_person_agrees(table, command_id="person-agrees"):
    return vote(table, TABLE_ABORT_AGREE_SUFFIX, command_id)


def the_agent_agrees(table, command_id="agent-agrees"):
    return table.staying.call(AGREE_TO_ABORT_HAND_TOOL, table_id=table.table_id, command_id=command_id)


def the_staying_agent_is_sent_away(table):
    sender = Actor(table.person.id, table.person.username)
    command = SendAway("command-away-staying", table.table_id, table.skat.stores.accounts.get(table.staying.subject).id)
    assert table.skat.tables.send_away(sender, command, frozenset({sender.account_id}), is_member=True).refusal is None


class TestTheVote:
    def test_a_yes_proposes_and_every_viewer_reads_the_seats_that_said_yes(self, waiting):
        answer = the_person_agrees(waiting)

        assert answer.status_code == 200, answer.text
        hand = answer.json()["hand"]
        assert (hand["abort"], hand["abortable"], answer.json()["aborted"]) == ([3], True, None)
        assert waiting.staying.read(waiting.table_id).json()["hand"]["abort"] == [3]

    def test_the_second_yes_of_two_seated_ends_the_hand_with_no_entry_and_no_result(self, waiting):
        the_person_agrees(waiting)

        ended = the_agent_agrees(waiting)

        assert not ended.is_error, ended.text
        view = waiting.staying.read(waiting.table_id).json()
        assert (view["hand"], view["aborted"], view["result"], view["passed_in"]) == (
            None,
            {"next_dealer_seat": None},
            None,
            None,
        )
        assert [chair["occupant_name"] is None for chair in view["chairs"]] == [False, True, False]
        assert waiting.person_reads()["aborted"] == {"next_dealer_seat": None}

    def test_a_no_of_the_agent_clears_the_proposal(self, waiting):
        the_person_agrees(waiting)

        refused = waiting.staying.call(REFUSE_TO_ABORT_HAND_TOOL, table_id=waiting.table_id, command_id="agent-refuses")

        assert not refused.is_error, refused.text
        assert waiting.person_reads()["hand"]["abort"] is None

    def test_a_person_refuses_with_the_route(self, waiting):
        the_agent_agrees(waiting)

        answer = vote(waiting, TABLE_ABORT_REFUSE_SUFFIX, "person-refuses")

        assert (answer.status_code, answer.json()["hand"]["abort"]) == (200, None)

    def test_the_same_command_id_twice_is_one_vote(self, waiting):
        first = the_person_agrees(waiting)

        again = the_person_agrees(waiting)

        assert (again.status_code, again.json()["version"]) == (200, first.json()["version"])

    def test_the_send_away_of_a_non_voting_agent_completes_the_majority_in_its_version(self, waiting):
        proposed = the_person_agrees(waiting)

        the_staying_agent_is_sent_away(waiting)

        read = waiting.person_reads()
        assert (read["hand"], read["aborted"], read["version"]) == (
            None,
            {"next_dealer_seat": None},
            proposed.json()["version"] + 1,
        )


class TestRefusals:
    def test_a_hand_with_no_open_chair_refuses_hand_not_open(self, skat, issuer):
        table = WaitingTable(skat, issuer)

        answer = the_person_agrees(table)

        assert (answer.status_code, answer.json()["reason"]) == (409, "hand-not-open")

    def test_someone_who_is_not_seated_refuses_not_seated(self, waiting):
        outsider_headers, _ = waiting.skat.member()

        answer = vote(waiting, TABLE_ABORT_AGREE_SUFFIX, "outsider-agrees", outsider_headers)

        assert (answer.status_code, answer.json()["reason"]) == (409, "not-seated")

    def test_a_no_with_nothing_standing_refuses_no_proposal(self, waiting):
        answer = vote(waiting, TABLE_ABORT_REFUSE_SUFFIX, "person-refuses")

        assert (answer.status_code, answer.json()["reason"]) == (409, "no-proposal")
