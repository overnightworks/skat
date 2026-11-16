"""The pods of one app share the place store on one real Redis: an agent that listens at one pod listens at the other,
and the other pod is told when it starts to."""

import asyncio

import pytest
from agents.mcp_server import ResourceChanges
from agents.member import STANDING_URI
from agents.tools import Principal

from skat.store.redis_clients import shared_place_store

pytestmark = pytest.mark.redis

NOVA = Principal(iss="an-issuer", sub="agent-nova")
TURN_WITHIN_SECONDS = 10


class Pod:
    """One pod's changes over a place store of its own client, and the turns it is told."""

    def __init__(self, redis_url):
        self.turns = asyncio.Queue()
        self.changes = ResourceChanges(
            shared_place_store(redis_url),
            listening_changed=lambda principal, uri, listens: self.turns.put_nowait((principal, uri, listens)),
        )

    async def next_turn(self):
        async with asyncio.timeout(TURN_WITHIN_SECONDS):
            return await self.turns.get()


class TestPodsOnARealRedis:
    def test_an_agent_that_starts_to_listen_at_one_pod_is_listening_at_the_other_and_the_other_is_told(self, redis_url):
        async def scenario():
            first, second = Pod(redis_url), Pod(redis_url)
            async with (
                first.changes.following(),
                second.changes.following(),
                first.changes.opened(NOVA) as stream,
            ):
                await first.changes.acknowledged(NOVA, stream, [STANDING_URI], tools=False)

                return (
                    await second.next_turn(),
                    await second.changes.listens_to(NOVA, STANDING_URI),
                    await second.changes.listeners(STANDING_URI),
                )

        assert asyncio.run(scenario()) == ((NOVA, STANDING_URI, True), True, frozenset({NOVA}))
