"""An agent states what its turns at a table do with `set_turn_state`: kept for the chair it holds, refused as
`not_held` without one, told to every viewer of the table and untouched by the table's version.
"""

import copy

import pytest
from agents.mcp_server.route_call import ARGUMENTS_REFUSED_TEXT
from agents.member import SET_TURN_STATE_TOOL

from skat.table.turn_state import THINKING_CAP_SECONDS
from tests.web.support.skat import Skat, streams_of

AGENTS_SEAT = 2
NOT_HELD = {"refused": "not_held"}


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def table(skat):
    """A table a person opened and sits at, with its headers and id."""
    headers, _ = skat.member()
    table_id = skat.create(headers).json()["id"]
    skat.client.cookies.clear()
    return headers, table_id


@pytest.fixture
def seated(agent, table):
    """The agent sits at chair 2 of the person's table."""
    _, table_id = table
    assert not agent.sit_down(table_id, AGENTS_SEAT).is_error
    return table_id


def place_of(table_id):
    return {"kind": "table", "id": table_id}


def state(agent, table_id, **statement):
    return agent.call(SET_TURN_STATE_TOOL, place=place_of(table_id), **statement)


def statement_at(skat, table_id, seat=AGENTS_SEAT):
    return skat.store.tables[table_id].chairs[seat - 1].turn_state


def test_a_seated_agents_statement_is_kept_for_its_chair_and_answers_empty(skat, agent, seated):
    answer = state(agent, seated, stopped="budget_spent")

    assert (answer.is_error, answer.json()) == (False, {})
    assert statement_at(skat, seated).stopped == "budget_spent"


def test_thinking_is_kept_as_the_chairs_value(skat, agent, seated):
    state(agent, seated, thinking=True)

    statement = statement_at(skat, seated)
    assert (statement.stopped, statement.thinking) == (None, True)


def test_the_next_statement_replaces_the_last(skat, agent, seated):
    state(agent, seated, thinking=True)
    state(agent, seated, stopped="busy")
    state(agent, seated)

    statement = statement_at(skat, seated)
    assert (statement.stopped, statement.thinking) == (None, False)


def test_the_tables_version_is_left_alone(skat, agent, seated):
    version = skat.store.tables[seated].version

    state(agent, seated, stopped="unavailable")

    assert skat.store.tables[seated].version == version


def test_an_agent_without_a_chair_at_the_table_is_refused_as_not_held_and_nothing_is_kept(skat, agent, seated):
    headers, _ = skat.member()
    other_table = skat.create(headers).json()["id"]
    before = copy.deepcopy(skat.store.tables[other_table])

    answer = state(agent, other_table, stopped="busy")

    assert (answer.is_error, answer.json()) == (True, NOT_HELD)
    assert skat.store.tables[other_table] == before
    assert statement_at(skat, seated) is None


def test_an_agent_that_left_its_only_chair_is_refused_as_not_held(skat, agent, seated):
    agent.stand_up(seated)

    answer = state(agent, seated, stopped="busy")

    assert (answer.is_error, answer.json()) == (True, NOT_HELD)
    assert statement_at(skat, seated) is None


@pytest.mark.parametrize(
    "place",
    [{"kind": "call", "id": "any"}, {"kind": "table", "id": "0" * 32}, {"kind": "table", "id": "no table id"}],
    ids=["another kind of place", "a table that is not there", "an id that is no table's"],
)
def test_a_place_that_is_no_table_of_the_agent_is_refused_as_not_held(agent, seated, place):
    answer = agent.call(SET_TURN_STATE_TOOL, place=place, stopped="busy")

    assert (answer.is_error, answer.json()) == (True, NOT_HELD)


@pytest.mark.parametrize(
    "statement",
    [{"stopped": "busy", "thinking": True}, {"stopped": "tired"}, {"thinking": "yes"}],
    ids=["both stopped and thinking", "an outcome nobody names", "a thinking that is no bool"],
)
def test_a_statement_the_agents_record_refuses_is_refused_and_nothing_is_kept(skat, agent, seated, statement):
    answer = state(agent, seated, **statement)

    assert answer.is_error
    assert answer.text.startswith(ARGUMENTS_REFUSED_TEXT)
    assert statement_at(skat, seated) is None


def test_the_agent_stands_up_and_its_statement_goes_with_its_chair(skat, agent, seated):
    state(agent, seated, stopped="busy")

    agent.stand_up(seated)

    assert statement_at(skat, seated) is None


def test_a_statement_reaches_every_stream_of_the_table_with_the_value_and_the_seconds_thinking_has_left(
    skat, agent, table, seated
):
    headers, table_id = table
    with streams_of(skat, table_id, [(headers, None)]) as [messages]:
        state(agent, table_id, thinking=True)
        thinking = next(messages)["chairs"][AGENTS_SEAT - 1]["turn_state"]
        state(agent, table_id, stopped="busy")
        stopped = next(messages)["chairs"][AGENTS_SEAT - 1]["turn_state"]

    assert thinking["stopped"] is None
    assert 0 < thinking["thinking_seconds_left"] <= THINKING_CAP_SECONDS
    assert stopped == {"stopped": "busy", "thinking_seconds_left": None}
