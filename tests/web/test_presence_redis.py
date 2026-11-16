"""The presences of two pods on one real Redis: one account's streams count once, and a stream that ended on one pod
wakes the table's streams on the other.
"""

import asyncio

import pytest

from skat.store.redis_clients import shared_stream_leases
from skat.web.wakes import TableTopic
from tests.support.idle_presence import idle_presence, idle_wakes

pytestmark = pytest.mark.redis

TABLE = "t" * 32
WOKEN_WITHIN_SECONDS = 15


def pods_on(redis_url, wakes=None):
    return (
        idle_presence(leases=shared_stream_leases(redis_url)),
        idle_presence(wakes=wakes, leases=shared_stream_leases(redis_url)),
    )


class TestOneAccountAsTwoHolders:
    def test_counts_as_one_watcher_on_both_pods_until_its_last_stream_closes(self, redis_url):
        first, second = pods_on(redis_url)

        async def scenario():
            here = await first.subscribe(TABLE, "anna", lambda: None)
            there = await second.subscribe(TABLE, "anna", lambda: None)
            both = await first.connected(TABLE), await second.connected(TABLE)
            await first.close(here)
            remaining = await second.connected(TABLE)
            await second.close(there)
            return both, remaining, await first.connected(TABLE)

        both, remaining, after = asyncio.run(scenario())

        assert (both, remaining, after) == (({"anna"}, {"anna"}), {"anna"}, frozenset())

    def test_is_listed_by_table_from_one_read(self, redis_url):
        first, second = pods_on(redis_url)

        async def scenario():
            await first.subscribe(TABLE, "anna", lambda: None)
            await second.subscribe("o" * 32, "ben", lambda: None)
            return await first.connected_at([TABLE, "o" * 32])

        assert asyncio.run(scenario()) == {TABLE: {"anna"}, "o" * 32: {"ben"}}


class TestALapse:
    def test_of_a_stream_ended_on_one_pod_wakes_the_streams_of_the_table_on_another(self, redis_url):
        wakes = idle_wakes()
        first, second = pods_on(redis_url, wakes)

        async def scenario():
            arrived = asyncio.Event()
            wakes.register([TableTopic(TABLE)], arrived.set)
            await first.close(await first.subscribe(TABLE, "anna", lambda: None))
            serving = asyncio.create_task(second.serve_lapses())
            try:
                async with asyncio.timeout(WOKEN_WITHIN_SECONDS):
                    await arrived.wait()
            finally:
                serving.cancel()

        asyncio.run(scenario())
