"""Two presences on one real Redis, as two pods: each counts the other's streams and decides with them."""

import asyncio

import pytest

from skat.store.redis_clients import shared_stream_leases
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.web.support.presence import HOLD_SECONDS, TABLE

pytestmark = pytest.mark.redis


@pytest.fixture
def leases(redis_url):
    return shared_stream_leases(redis_url)


@pytest.fixture
def run():
    """Runs scenarios one after the other on one event loop, which the Redis client's connections are bound to."""
    with asyncio.Runner() as runner:
        yield runner.run


@pytest.fixture
def connect(run):
    return lambda presence, table_id, account_id, wake: run(presence.subscribe(table_id, account_id, wake))


class TestWhoIsConnected:
    def test_a_stream_on_one_pod_counts_on_the_other(self, run, connect, holding, elsewhere):
        connect(elsewhere, TABLE, "anna", lambda: None)

        assert run(holding.connected(TABLE)) == {"anna"}


class TestTheHoldOfAChair:
    def test_does_not_start_while_the_account_has_a_stream_on_the_other_pod(
        self, run, connect, holding, elsewhere, wakes
    ):
        connect(elsewhere, TABLE, "anna", lambda: None)
        leaving = connect(holding, TABLE, "anna", wakes.callback("anna"))
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        before = dict(wakes.counts)

        run(holding.close(leaving))

        assert holding.hold_seconds_left([TABLE]) == {}
        assert wakes.counts == before

    def test_starts_when_the_last_stream_of_the_account_on_any_pod_closes(self, run, connect, holding, elsewhere):
        here = connect(holding, TABLE, "anna", lambda: None)
        there = connect(elsewhere, TABLE, "anna", lambda: None)
        run(elsewhere.close(there))

        run(holding.close(here))

        assert holding.hold_seconds_left([TABLE]) == {TABLE: {"anna": HOLD_SECONDS}}

    def test_frees_no_chair_whose_account_came_back_on_the_other_pod(
        self, run, connect, holding, elsewhere, time, releases
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        connect(elsewhere, TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == [False]


class TestAnEmptyTable:
    def test_is_ended_with_who_is_connected_on_the_other_pod_so_that_the_decision_refuses(
        self, run, connect, holding, elsewhere, time, ends
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        connect(elsewhere, TABLE, "ben", lambda: None)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == [(TABLE, {"ben"})]
