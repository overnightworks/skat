"""Two presences on one real Redis, as two pods: each counts the other's streams and decides with them."""

import asyncio

import pytest

from skat.store.redis_clients import shared_stream_leases
from skat.web.presence import HOLD_SWEEP_EVERY_SECONDS
from tests.support.redis import settle_wake_epoch
from tests.web.support.presence import TABLE

pytestmark = pytest.mark.redis


@pytest.fixture
def run():
    """Runs scenarios one after the other on one event loop, which the Redis client's connections are bound to."""
    with asyncio.Runner() as runner:
        yield runner.run


@pytest.fixture
def leases(redis_url, run):
    """The shared leases on a Redis whose restart grace is over: a roster without a person then means they are gone."""

    run(settle_wake_epoch(redis_url))
    return shared_stream_leases(redis_url)


@pytest.fixture
def connect(run):
    return lambda presence, table_id, account_id, wake: run(presence.subscribe(table_id, account_id, wake))


class TestWhoIsConnected:
    def test_a_stream_on_one_pod_counts_on_the_other(self, run, connect, holding, elsewhere):
        connect(elsewhere, TABLE, "anna", lambda: None)

        assert run(holding.connected(TABLE)) == {"anna"}


class TestTheHoldOfAChair:
    def test_frees_no_chair_whose_account_came_back_on_the_other_pod(
        self, run, connect, holding, elsewhere, time, holds
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        connect(elsewhere, TABLE, "anna", lambda: None)
        holds.due_now = list(holds.left)

        holding.start_sweeps()
        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert holds.outcomes == [False]


class TestAnEmptyTable:
    def test_is_ended_with_who_is_connected_on_the_other_pod_so_that_the_decision_refuses(
        self, run, connect, holding, elsewhere, time, ends
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        connect(elsewhere, TABLE, "ben", lambda: None)
        ends.due_now = [TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert ends.calls == [(TABLE, {"ben"})]
