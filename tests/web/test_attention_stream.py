"""The event `attention` of the table stream: one whole number, the account's other live tables that wait for it."""

from itertools import count
from random import Random

import pytest

from skat.table.records import Actor
from skat.table.service import TableService
from skat.web.streams import SourceMessage, StreamEvent
from skat.web.wakes import AccountTopic, TableTopic
from tests.support.fake_tables import FakeTableStore
from tests.web.support.lobby_scene import DAYS, Scene
from tests.web.support.streams import run_on_a_loop_of_its_own

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")


def waits_for(scene, person):
    held = scene.service.tables_held_by(person.account_id)
    return [entry.awaits_you for entry in scene.service.my_tables(person.account_id, held, {}, DAYS)]


def a_seed_where_the_deal_gives_anna_the_turn():
    for seed in count():
        scene = Scene(TableService(FakeTableStore(), random_source=Random(seed)))
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)
        if waits_for(scene, ANNA) == [True]:
            return seed
    raise AssertionError  # pragma: no cover - the loop returns


@pytest.fixture
def scene():
    return Scene(TableService(FakeTableStore(), random_source=Random(a_seed_where_the_deal_gives_anna_the_turn())))


def deal_at_a_table_of_three(scene):
    table_id = scene.open_table(ANNA)
    scene.sit(BEN, table_id, 2)
    scene.sit(CLEO, table_id, 3)
    return table_id


async def next_attention(stream):
    item = await anext(stream)
    assert isinstance(item, SourceMessage)
    assert item.event is StreamEvent.ATTENTION
    return item.data


class TestWhatIsCounted:
    def test_a_table_that_waits_for_the_person_counts_one_at_the_table_he_sits_at_alone(self, scene):
        deal_at_a_table_of_three(scene)
        solo = scene.open_table(ANNA)

        async def scenario():
            stream = scene.attention_stream(ANNA, solo)
            number = await next_attention(stream)
            await stream.aclose()
            return number

        assert run_on_a_loop_of_its_own(scenario()) == "1"

    def test_the_table_the_stream_belongs_to_is_not_counted(self, scene):
        table_id = deal_at_a_table_of_three(scene)

        async def scenario():
            stream = scene.attention_stream(ANNA, table_id)
            number = await next_attention(stream)
            await stream.aclose()
            return number

        assert run_on_a_loop_of_its_own(scenario()) == "0"

    @pytest.mark.parametrize("person", [BEN, CLEO, DORA], ids=["another seat", "a third seat", "no chair"])
    def test_a_table_that_waits_for_another_member_never_counts_for_him(self, scene, person):
        deal_at_a_table_of_three(scene)
        elsewhere = scene.open_table(DORA)

        async def scenario():
            stream = scene.attention_stream(person, elsewhere)
            number = await next_attention(stream)
            await stream.aclose()
            return number

        assert run_on_a_loop_of_its_own(scenario()) == "0"

    def test_a_person_without_a_chair_at_the_table_he_watches_gets_the_count_of_his_own_tables(self, scene):
        deal_at_a_table_of_three(scene)
        watched = scene.open_table(DORA)

        async def scenario():
            stream = scene.attention_stream(ANNA, watched)
            number = await next_attention(stream)
            await stream.aclose()
            return number

        assert run_on_a_loop_of_its_own(scenario()) == "1"

    def test_a_table_that_does_not_wait_yet_counts_nothing_until_a_deal_makes_it_wait(self, scene):
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)
        solo = scene.open_table(ANNA)

        async def scenario():
            stream = scene.attention_stream(ANNA, solo)
            before = await next_attention(stream)
            scene.sit(CLEO, table_id, 3)
            after = await next_attention(stream)
            await stream.aclose()
            return before, after

        assert run_on_a_loop_of_its_own(scenario()) == ("0", "1")

    def test_leaving_the_table_that_waits_takes_the_number_down_again(self, scene):
        table_id = deal_at_a_table_of_three(scene)
        solo = scene.open_table(ANNA)

        async def scenario():
            stream = scene.attention_stream(ANNA, solo)
            before = await next_attention(stream)
            scene.stand(ANNA, table_id)
            after = await next_attention(stream)
            await stream.aclose()
            return before, after

        assert run_on_a_loop_of_its_own(scenario()) == ("1", "0")


class TestTheWakes:
    def test_a_commit_at_the_table_of_the_stream_does_not_wake_it_and_one_at_another_table_of_the_person_does(
        self, scene
    ):
        own = scene.open_table(ANNA)
        other = deal_at_a_table_of_three(scene)
        woken = []

        async def scenario():
            source = scene.attention_source(ANNA, own)
            await source.open(lambda: woken.append(1))
            await source.read(ANNA)
            scene.presence.wake_table(own)
            at_its_own_table = len(woken)
            scene.presence.wake_table(other)
            source.close()
            return at_its_own_table, len(woken)

        assert run_on_a_loop_of_its_own(scenario()) == (0, 1)

    def test_the_account_topic_wakes_it_so_a_table_the_person_sits_down_at_is_counted(self, scene):
        own = scene.open_table(ANNA)
        woken = []

        async def scenario():
            source = scene.attention_source(ANNA, own)
            await source.open(lambda: woken.append(1))
            await source.read(ANNA)
            scene.wakes.wake(AccountTopic(ANNA.account_id))
            source.close()
            return len(woken)

        assert run_on_a_loop_of_its_own(scenario()) == 1

    def test_no_topic_is_left_registered_once_it_closes(self, scene):
        own = scene.open_table(ANNA)
        other = deal_at_a_table_of_three(scene)
        woken = []

        async def scenario():
            source = scene.attention_source(ANNA, own)
            await source.open(lambda: woken.append(1))
            await source.read(ANNA)
            source.close()
            scene.wakes.wake(AccountTopic(ANNA.account_id))
            scene.wakes.wake(TableTopic(other))
            return len(woken)

        assert run_on_a_loop_of_its_own(scenario()) == 0
