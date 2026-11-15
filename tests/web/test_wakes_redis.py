"""The pods of one app follow one real Redis channel: a wake at one reaches the other, and a pod whose subscription
Redis ended re-reads everything it serves when it is subscribed again."""

import pytest
from redis import Redis

from skat.store.redis_clients import shared_wake_channel
from skat.web.wakes import TableTopic
from tests.web.support.wake_pods import run_pods

pytestmark = pytest.mark.redis

TABLE = TableTopic("c" * 32)


def real_pods(redis_url, scenario):
    run_pods([shared_wake_channel(redis_url), shared_wake_channel(redis_url)], scenario)


class TestPodsOnARealRedis:
    def test_a_wake_at_one_pod_reaches_the_registrations_of_its_topic_at_the_other(self, redis_url):
        async def scenario(first, second):
            second.listen("second", TABLE)

            first.wake_list.wake(TABLE)

            await second.arrival_of("second")

        real_pods(redis_url, scenario)

    def test_a_pod_whose_subscription_redis_ended_wakes_every_registration_when_it_is_subscribed_again(self, redis_url):
        async def scenario(_first, second):
            second.listen("table", TABLE)
            with Redis.from_url(redis_url) as redis:
                redis.client_kill_filter(_type="pubsub")

            await second.arrival_of("table")

        real_pods(redis_url, scenario)
