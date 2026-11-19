"""The pods of one app share the record of an agent's name and owner on one real Redis."""

import asyncio

import pytest
from agents.member import LEASE_SECONDS
from redis.asyncio import Redis
from redis.exceptions import RedisError
from webauth.ports import AgentFacts

from skat.store.redis_agent_records import record_key
from skat.store.redis_clients import AGENT_RECORD_KEY_PREFIX, shared_agent_records

pytestmark = pytest.mark.redis

NOVA = "account-nova"
BACH = "account-bach"
UNREACHABLE_URL = "redis://127.0.0.1:1/0"


def run(scenario):
    return asyncio.run(scenario)


class TestARecordOnARealRedis:
    def test_written_by_one_pod_is_read_by_another_with_the_name_and_owner(self, redis_url):
        async def scenario():
            await shared_agent_records(redis_url).write(NOVA, AgentFacts(owner="owner-felix", name="Nova"))
            return await shared_agent_records(redis_url).read([NOVA, BACH])

        assert run(scenario()) == {NOVA: AgentFacts(owner="owner-felix", name="Nova")}

    def test_the_writer_that_comes_last_wins(self, redis_url):
        async def scenario():
            records = shared_agent_records(redis_url)
            await records.write(NOVA, AgentFacts(owner="owner-felix", name="Nova"))
            await shared_agent_records(redis_url).write(NOVA, AgentFacts(owner="owner-anna", name="Nova2"))
            return await records.read([NOVA])

        assert run(scenario()) == {NOVA: AgentFacts(owner="owner-anna", name="Nova2")}

    def test_reading_no_account_reads_nothing(self, redis_url):
        assert run(shared_agent_records(redis_url).read([])) == {}

    def test_a_record_expires_within_the_lease_of_its_latest_write(self, redis_url):
        async def scenario():
            await shared_agent_records(redis_url).write(NOVA, AgentFacts(owner="owner-felix", name="Nova"))
            async with Redis.from_url(redis_url) as client:  # pyright: ignore[reportUnknownMemberType]
                return await client.ttl(record_key(AGENT_RECORD_KEY_PREFIX, NOVA))

        assert 0 < run(scenario()) <= LEASE_SECONDS

    @pytest.mark.parametrize("stored", ["not json", '{"name": "Nova"}', '{"name": 1, "owner": "owner-felix"}'])
    def test_a_value_that_is_no_record_is_left_out(self, redis_url, stored):
        async def scenario():
            async with Redis.from_url(redis_url) as client:  # pyright: ignore[reportUnknownMemberType]
                await client.set(record_key(AGENT_RECORD_KEY_PREFIX, NOVA), stored)
            return await shared_agent_records(redis_url).read([NOVA])

        assert run(scenario()) == {}

    def test_a_redis_that_does_not_answer_raises_at_a_write_and_at_a_read(self):
        records = shared_agent_records(UNREACHABLE_URL)

        with pytest.raises(RedisError):
            run(records.write(NOVA, AgentFacts(owner="owner-felix", name="Nova")))
        with pytest.raises(RedisError):
            run(records.read([NOVA]))
        with pytest.raises(RedisError):
            run(records.delete(NOVA))

    def test_a_deleted_record_is_no_longer_read(self, redis_url):
        async def scenario():
            records = shared_agent_records(redis_url)
            await records.write(NOVA, AgentFacts(owner="owner-felix", name="Nova"))
            await records.delete(NOVA)
            return await records.read([NOVA])

        assert run(scenario()) == {}
