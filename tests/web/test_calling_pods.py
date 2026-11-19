"""An agent that listens on one pod is listed, called and sent away from a page the other pod serves, under the key
either pod gave.
"""

import pytest

from skat.web.calling import CallRefusal
from tests.web.support.agent import Agent
from tests.web.support.calling import (
    call,
    invitations_of,
    listening,
    only_row,
    person,
    read_control,
    send_away,
)
from tests.web.support.shared_pods import running_pods
from tests.web.support.skat import streams_of

NOVA = "agent-nova"


@pytest.fixture
def pods(hold, issuer, time):
    with running_pods(2, hold, issuer, time) as running:
        yield running


@pytest.fixture
def felix(pods, issuer):
    return person(pods[0], issuer)


@pytest.fixture
def table_id(pods, felix):
    created = pods[0].create(felix.headers)
    pods[0].client.cookies.clear()
    return created.json()["id"]


@pytest.fixture(autouse=True)
def watching(pods, felix, table_id):
    """Felix has an open stream on his table, which every pod counts."""
    with streams_of(pods[0], table_id, [(felix.headers, None)]):
        yield


def names_of_rows(pod, who, table_id):
    return [row["name"] for row in read_control(pod, who, table_id).json()["rows"]]


def chair_two(pod, table_id):
    return pod.store.tables[table_id].chairs[1].occupant


@pytest.mark.parametrize(("listens_on", "page_on"), [(0, 1), (1, 0)], ids=["listens-on-a", "listens-on-b"])
def test_an_agent_listening_on_one_pod_is_listed_on_a_page_the_other_serves(
    pods, issuer, felix, table_id, listens_on, page_on
):
    with listening(pods[listens_on], issuer, felix, "Nova", NOVA):
        assert names_of_rows(pods[page_on], felix, table_id) == ["Nova"]


def test_a_key_one_pod_gave_calls_the_agent_through_the_other(pods, issuer, felix, table_id):
    with listening(pods[0], issuer, felix, "Nova", NOVA) as nova:
        key = only_row(pods[0], felix, table_id)["key"]

        answer = call(pods[1], felix, table_id, key)

        assert answer.status_code == 200
        assert len(invitations_of(nova)) == 1


def test_a_key_one_pod_gave_sends_a_seated_agent_away_through_the_other(pods, issuer, felix, table_id):
    with listening(pods[0], issuer, felix, "Nova", NOVA) as nova:
        nova.sit_down(table_id, 2)
        key = only_row(pods[0], felix, table_id)["key"]

        answer = send_away(pods[1], felix, table_id, key)

        assert answer.status_code == 200
        assert chair_two(pods[1], table_id) is None


def test_a_seated_agent_that_stopped_calling_is_sent_away_from_the_other_pod(pods, issuer, felix, table_id):
    nova = Agent(pods[0], issuer, NOVA, agent_owner=felix.id, agent_name="Nova")
    nova.sit_down(table_id, 2)
    row = only_row(pods[0], felix, table_id)

    answer = send_away(pods[1], felix, table_id, row["key"])

    assert (row["state"], answer.status_code, chair_two(pods[1], table_id)) == ("here", 200, None)


def test_a_send_away_replayed_on_the_other_pod_answers_as_the_first_did(pods, issuer, felix, table_id):
    with listening(pods[0], issuer, felix, "Nova", NOVA) as nova:
        nova.sit_down(table_id, 2)
        key = only_row(pods[0], felix, table_id)["key"]

        first = send_away(pods[0], felix, table_id, key, "command-same-tap")
        replayed = send_away(pods[1], felix, table_id, key, "command-same-tap")

        assert (first.status_code, replayed.status_code) == (200, 200)
        assert first.json() == replayed.json()


def test_a_key_stays_the_same_when_the_agent_listens_again_and_on_either_pod(pods, issuer, felix, table_id):
    with listening(pods[0], issuer, felix, "Nova", NOVA):
        first = only_row(pods[0], felix, table_id)["key"]
        on_the_other = only_row(pods[1], felix, table_id)["key"]
    with listening(pods[1], issuer, felix, "Nova", NOVA):
        again = only_row(pods[0], felix, table_id)["key"]

    assert first == on_the_other == again


def test_a_store_that_does_not_answer_offers_no_agent(pods, issuer, felix, table_id):
    with listening(pods[0], issuer, felix, "Nova", NOVA):
        pods[0].shared.place_store.unreachable = True
        while_down = names_of_rows(pods[1], felix, table_id)
        pods[0].shared.place_store.unreachable = False

        assert (while_down, names_of_rows(pods[1], felix, table_id)) == ([], ["Nova"])


def test_a_call_with_a_key_nobody_was_given_is_agent_unavailable(pods, issuer, felix, table_id):
    with listening(pods[0], issuer, felix, "Nova", NOVA):
        answer = call(pods[1], felix, table_id, "a-key-no-pod-made")

        assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.AGENT_UNAVAILABLE})
