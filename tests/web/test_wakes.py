import asyncio

import pytest
from structlog.testing import capture_logs
from tandem import Resubscribed, StoreError, Wake

from skat.web import wakes as wakes_module
from skat.web.secret_files import StartRefusedError
from skat.web.wakes import AccountTopic, OpenTablesTopic, TableTopic
from tests.support.idle_presence import idle_wakes
from tests.support.loopback_wake_channel import LoopbackWakeBus
from tests.web.support.presence import Wakes
from tests.web.support.wake_pods import ARRIVAL_SECONDS, Pod, run_pods

FIRST_TABLE = TableTopic("a" * 32)
SECOND_TABLE = TableTopic("b" * 32)
# More event-loop turns than leaving takes, so that only waiting for the publish lets it arrive.
SLOW_PUBLISH_TURNS = 50
ANNA = AccountTopic("account-anna")
OTHER_ACCOUNT = AccountTopic("account-other")


@pytest.fixture
def wakes():
    return Wakes()


class TestWakeList:
    def test_a_wake_reaches_the_registrations_of_its_topic_and_no_other(self, wakes):
        wake_list = idle_wakes()
        wake_list.register([FIRST_TABLE], wakes.callback("first"))
        wake_list.register([FIRST_TABLE], wakes.callback("also first"))
        wake_list.register([SECOND_TABLE], wakes.callback("second"))

        wake_list.wake(FIRST_TABLE)

        assert wakes.counts == {"first": 1, "also first": 1, "second": 0}

    def test_an_account_topic_and_a_table_topic_wake_only_their_own_registrations(self, wakes):
        wake_list = idle_wakes()
        wake_list.register([ANNA, FIRST_TABLE], wakes.callback("anna and first"))
        wake_list.register([FIRST_TABLE], wakes.callback("first"))
        wake_list.register([AccountTopic(FIRST_TABLE.table_id)], wakes.callback("an account named like the table"))

        wake_list.wake(ANNA)

        assert wakes.counts == {"anna and first": 1, "first": 0, "an account named like the table": 0}

    def test_a_wake_spares_the_registration_it_names(self, wakes):
        wake_list = idle_wakes()
        spared = wake_list.register([FIRST_TABLE], wakes.callback("spared"))
        wake_list.register([FIRST_TABLE], wakes.callback("other"))

        wake_list.wake(FIRST_TABLE, sparing=spared)

        assert wakes.counts == {"spared": 0, "other": 1}

    def test_an_unregistered_registration_is_no_longer_woken(self, wakes):
        wake_list = idle_wakes()
        ended = wake_list.register([FIRST_TABLE, SECOND_TABLE], wakes.callback("ended"))
        wake_list.register([FIRST_TABLE], wakes.callback("kept"))

        wake_list.unregister(ended)
        wake_list.wake(FIRST_TABLE)
        wake_list.wake(SECOND_TABLE)

        assert wakes.counts == {"ended": 0, "kept": 1}

    def test_wake_all_reaches_every_registration_once(self, wakes):
        wake_list = idle_wakes()
        wake_list.register([FIRST_TABLE, SECOND_TABLE], wakes.callback("both"))
        wake_list.register([SECOND_TABLE], wakes.callback("second"))

        wake_list.wake_all()

        assert wakes.counts == {"both": 1, "second": 1}


def between_pods(scenario, *, pods=2):
    """Runs `scenario(bus, *pods)` on pods that follow one bus."""
    bus = LoopbackWakeBus()
    channels = [bus.pod() for _ in range(pods)]
    run_pods(channels, lambda *pod_list: scenario(bus, *pod_list))
    return bus


class TestSharedWakes:
    @pytest.mark.parametrize("topic", [FIRST_TABLE, ANNA, OpenTablesTopic()], ids=["table", "account", "open-tables"])
    def test_a_wake_at_one_pod_wakes_the_registrations_of_its_topic_at_the_other_and_no_other(self, topic):
        async def scenario(_bus, first, second):
            second.listen("same topic", topic)
            second.listen("other topic", OTHER_ACCOUNT)
            second.listen("marker", SECOND_TABLE)

            first.wake_list.wake(topic)
            first.wake_list.wake(SECOND_TABLE)
            await second.arrival_of("marker")

            assert second.woken == {"same topic": 1, "marker": 1}

        between_pods(scenario)

    def test_a_wake_wakes_the_registrations_of_the_pod_that_woke_at_once_and_spares_the_one_it_names(self):
        async def scenario(_bus, first, second):
            spared = first.listen("spared", FIRST_TABLE)
            first.listen("local", FIRST_TABLE)
            second.listen("second", FIRST_TABLE)

            first.wake_list.wake(FIRST_TABLE, sparing=spared)

            assert first.woken == {"local": 1}
            await second.arrival_of("second")

        between_pods(scenario)

    def test_a_wake_that_arrives_wakes_locally_and_is_published_no_more(self):
        async def scenario(bus, first, second):
            first.listen("first", FIRST_TABLE)
            second.listen("second", FIRST_TABLE)

            first.wake_list.wake(FIRST_TABLE)
            await second.arrival_of("second")
            await first.arrival_of("first", 2)
            await first.shared.drain()
            await second.shared.drain()

            assert len(bus.published) == 1

        between_pods(scenario)

    def test_a_resubscribe_wakes_every_registration_whatever_its_topic(self):
        async def scenario(_bus, first, _second):
            first.listen("table", FIRST_TABLE)
            first.listen("account", ANNA)

            first.channel.inbox.put_nowait(Resubscribed())

            await first.arrival_of("table")
            await first.arrival_of("account")

        between_pods(scenario)

    def test_an_address_that_names_no_topic_wakes_nothing_and_the_next_wake_still_arrives(self):
        async def scenario(_bus, first, second):
            second.listen("second", FIRST_TABLE)

            second.channel.inbox.put_nowait(Wake("not-a-topic"))
            first.wake_list.wake(FIRST_TABLE)
            await second.arrival_of("second")

            assert second.woken == {"second": 1}

        between_pods(scenario)

    def test_a_publish_that_fails_once_is_logged_by_its_type_and_sent_again(self):
        async def scenario(bus, first, second):
            second.listen("second", FIRST_TABLE)
            first.channel.failures_before_publishing.append(StoreError("secret detail"))

            with capture_logs() as logged:
                first.wake_list.wake(FIRST_TABLE)
                await second.arrival_of("second")

            assert [(entry["log_level"], entry["error"]) for entry in logged] == [("warning", "StoreError")]
            assert "secret detail" not in str(logged)
            assert len(bus.published) == 1

        between_pods(scenario)

    def test_a_publish_that_fails_twice_is_logged_and_the_change_stands(self):
        async def scenario(bus, first, _second):
            first.listen("local", FIRST_TABLE)
            first.channel.failures_before_publishing.extend([StoreError("one"), StoreError("two")])

            with capture_logs() as logged:
                first.wake_list.wake(FIRST_TABLE)
                await first.shared.drain()

            assert first.woken == {"local": 1}
            assert [entry["log_level"] for entry in logged] == ["warning", "error"]
            assert bus.published == []

        between_pods(scenario)

    def test_leaving_waits_for_the_publishes_that_are_pending(self):
        async def scenario(_bus, first, _second):
            first.channel.turns_before_publishing = SLOW_PUBLISH_TURNS
            first.wake_list.wake(FIRST_TABLE)

        bus = between_pods(scenario)

        assert len(bus.published) == 1

    def test_the_channel_ending_with_a_store_error_after_the_start_is_logged_by_its_type_and_ends_the_process(self):
        async def scenario(_bus, first, _second):
            with capture_logs() as logged:
                first.channel.inbox.put_nowait(StoreError("secret detail"))
                await asyncio.wait_for(first.ended.wait(), ARRIVAL_SECONDS)

            assert [(entry["log_level"], entry["error"]) for entry in logged] == [("error", "StoreError")]
            assert "secret detail" not in str(logged)

        between_pods(scenario)


class TestStartingToFollow:
    @staticmethod
    def silent_pod():
        return Pod(LoopbackWakeBus().pod(acknowledging=False))

    def test_serving_waits_for_the_first_resubscribe(self):
        async def run():
            pod = self.silent_pod()
            entered = []

            async def serve():
                async with pod.shared.following(pod.wake_list):
                    entered.append(True)

            serving = asyncio.create_task(serve())
            for _ in range(5):
                await asyncio.sleep(0)
            waiting = list(entered)
            pod.channel.inbox.put_nowait(Resubscribed())
            await asyncio.wait_for(serving, ARRIVAL_SECONDS)

            assert (waiting, entered) == ([], [True])

        asyncio.run(run())

    def test_a_start_without_a_resubscribe_within_the_bound_is_refused_naming_the_setting(self, monkeypatch):
        monkeypatch.setattr(wakes_module, "STARTUP_SECONDS", 0.05)

        async def run():
            pod = self.silent_pod()
            with pytest.raises(StartRefusedError, match="redis_url"):
                async with pod.shared.following(pod.wake_list):
                    pytest.fail("served without a subscription")

        asyncio.run(run())

    def test_a_start_whose_channel_fails_before_the_first_resubscribe_fails_with_that_error_and_ends_no_process(self):
        async def run():
            pod = self.silent_pod()
            pod.channel.inbox.put_nowait(StoreError("refused"))
            with pytest.raises(StoreError):
                async with pod.shared.following(pod.wake_list):
                    pytest.fail("served without a subscription")

            assert not pod.ended.is_set()

        asyncio.run(run())
