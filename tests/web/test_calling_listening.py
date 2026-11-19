"""The control's rows follow which agents listen as the place store tells it: a turn may repeat or come late, and a
turn lost while the subscription was down is read again at the next resync.
"""

from datetime import timedelta

import pytest
from agents.mcp_server.place_store import ListeningTurn
from agents.member import STANDING_URI
from agents.tools import Principal

from tests.support.sign_in_settings import TEST_ISSUER
from tests.web.support.agent import Agent
from tests.web.support.calling import CallingTable, listening, read_control

NOVA = "agent-nova"


def names_of_rows(skat, who, table_id):
    return [row["name"] for row in read_control(skat, who, table_id).json()["rows"]]


def principal_of(skat, subject):
    return Principal(iss=TEST_ISSUER, sub=skat.stores.accounts.get(subject).id)


@pytest.mark.usefixtures("watching")
class TestTheControlKeepsAnAgentThatStillListens(CallingTable):
    @pytest.mark.parametrize("repeats", [1, 3])
    def test_a_yes_the_store_tells_again_keeps_one_row(self, skat, issuer, changes, felix, table_id, repeats):
        with listening(skat, issuer, felix, "Nova", NOVA):
            principal = principal_of(skat, NOVA)
            for _ in range(repeats):
                skat.client.portal.call(changes.store.inject, ListeningTurn(principal, STANDING_URI, True))

            assert names_of_rows(skat, felix, table_id) == ["Nova"]

    def test_an_older_no_that_comes_after_the_listens_yes_does_not_hide_the_row_once_the_stores_yes_follows(
        self, skat, issuer, changes, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            principal = principal_of(skat, NOVA)
            skat.client.portal.call(changes.store.inject, ListeningTurn(principal, STANDING_URI, False))
            skat.client.portal.call(changes.store.inject, ListeningTurn(principal, STANDING_URI, True))

            assert names_of_rows(skat, felix, table_id) == ["Nova"]

    def test_a_no_for_an_agent_the_roster_never_listed_changes_nothing(self, skat, issuer, changes, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA):
            stranger = Principal(iss=TEST_ISSUER, sub="an-account-that-never-listened")
            skat.client.portal.call(changes.store.inject, ListeningTurn(stranger, STANDING_URI, False))

            assert names_of_rows(skat, felix, table_id) == ["Nova"]


@pytest.mark.usefixtures("watching")
class TestTheControlReadsWhoListensAgainAtEveryResync(CallingTable):
    def test_an_agent_that_started_to_listen_while_the_subscription_was_down_is_listed_after_the_resync(
        self, skat, issuer, changes, felix, table_id
    ):
        Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova").listed_resources()
        skat.client.portal.call(
            changes.store.record_without_turn,
            "a-stream-of-another-pod",
            principal_of(skat, NOVA),
            [STANDING_URI],
            timedelta(minutes=5),
        )
        rows_before = names_of_rows(skat, felix, table_id)

        skat.client.portal.call(changes.store.resubscribed)

        assert (rows_before, names_of_rows(skat, felix, table_id)) == ([], ["Nova"])

    def test_a_store_that_does_not_answer_at_a_resync_leaves_the_rows_as_the_turns_made_them(
        self, skat, issuer, changes, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            changes.store.unreachable = True
            skat.client.portal.call(changes.store.resubscribed)
            changes.store.unreachable = False

            assert names_of_rows(skat, felix, table_id) == ["Nova"]


@pytest.mark.usefixtures("watching")
class TestTheControlOffersNoAgentWhoseListenItCannotRead(CallingTable):
    def test_a_store_that_does_not_answer_leaves_the_control_with_no_row_until_it_answers_again(
        self, skat, issuer, changes, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            changes.store.unreachable = True
            rows_while_down = names_of_rows(skat, felix, table_id)
            changes.store.unreachable = False

            assert (rows_while_down, names_of_rows(skat, felix, table_id)) == ([], ["Nova"])
