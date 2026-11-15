"""The pods of one app follow one real Redis channel: a wake at one reaches the other, and a pod whose subscription
Redis ended re-reads everything it serves when it is subscribed again."""

from uuid import uuid4

import pytest

from skat.store.redis_clients import shared_wake_channel
from skat.web.wakes import TableTopic
from tests.support.redis import end_subscriptions
from tests.web.support.wake_pods import run_pods

pytestmark = pytest.mark.redis


def new_table_topic():
    """A topic of its own: the channel is the same for every worker's tests on the shared server."""
    return TableTopic(uuid4().hex)


def real_pods(redis_url, scenario):
    run_pods([shared_wake_channel(redis_url), shared_wake_channel(redis_url)], scenario)


class TestPodsOnARealRedis:
    def test_a_wake_at_one_pod_reaches_the_registrations_of_its_topic_at_the_other(self, redis_url):
        table = new_table_topic()

        async def scenario(first, second):
            second.listen("second", table)

            first.wake_list.wake(table)

            await second.arrival_of("second")

        real_pods(redis_url, scenario)

    def test_a_pod_whose_subscription_redis_ended_wakes_every_registration_when_it_is_subscribed_again(self, redis_url):
        table = new_table_topic()

        async def scenario(_first, second):
            second.listen("table", table)
            end_subscriptions(redis_url)

            await second.arrival_of("table")

        real_pods(redis_url, scenario)
