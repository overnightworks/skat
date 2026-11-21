"""An agent's lines and view carry the trace of the request that committed their act or version, never the trace of
the request that reads them, and carry none for a table that stored none.
"""

import json
from dataclasses import replace

import pytest

from skat.engine.deal import Position
from skat.table.records import EntryTraces
from tests.web.support.agent import view_uri_of, window_uri_of
from tests.web.support.skat import running_skat

COMMITTING_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
READING_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


@pytest.fixture
def skat(hold, issuer, time):
    yield from running_skat(hold, issuer, time)


def traceparent_of(trace_id):
    return f"00-{trace_id}-00f067aa0ba902b7-01"


def trace_id_of(traceparent):
    return traceparent.split("-")[1]


def read_in_a_trace(agent, uri):
    """What the agent reads at `uri`, in a request that has a trace of its own."""
    answer = agent.request(
        "resources/read", {"uri": uri}, extra_headers={"traceparent": traceparent_of(READING_TRACE_ID)}
    )
    assert answer.status_code == 200, answer.text
    return json.loads(answer.json()["result"]["contents"][0]["text"])


def a_bid_in_the_committing_trace(table):
    table.at[Position.MIDDLEHAND] = {
        **table.at[Position.MIDDLEHAND],
        "traceparent": traceparent_of(COMMITTING_TRACE_ID),
    }
    table.middlehand_bids()


class TestTheLineAndTheViewCarryTheCommittingTrace:
    def test_the_line_of_an_act_carries_the_trace_of_the_request_that_committed_it(self, agent, forehand_auction):
        a_bid_in_the_committing_trace(forehand_auction)

        deal, bid = read_in_a_trace(agent, window_uri_of(forehand_auction.table_id))["entries"]

        assert trace_id_of(bid["traceparent"]) == COMMITTING_TRACE_ID
        assert trace_id_of(deal["traceparent"]) != COMMITTING_TRACE_ID

    def test_the_view_carries_the_trace_of_the_request_that_moved_its_version(self, agent, forehand_auction):
        a_bid_in_the_committing_trace(forehand_auction)

        view = read_in_a_trace(agent, view_uri_of(forehand_auction.table_id))

        assert trace_id_of(view["traceparent"]) == COMMITTING_TRACE_ID

    def test_a_line_and_a_view_of_a_table_that_stored_no_trace_carry_none(self, skat, agent, forehand_auction):
        a_bid_in_the_committing_trace(forehand_auction)
        skat.store.tables[forehand_auction.table_id] = replace(forehand_auction.record, traces=EntryTraces())

        window = read_in_a_trace(agent, window_uri_of(forehand_auction.table_id))
        view = read_in_a_trace(agent, view_uri_of(forehand_auction.table_id))

        assert ["traceparent" in line for line in window["entries"]] + ["traceparent" in view] == [False, False, False]
