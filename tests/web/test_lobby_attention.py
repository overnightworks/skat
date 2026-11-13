"""The event `attention` of the table stream: one whole number, the account's other live tables that wait for it."""

from itertools import count
from random import Random

import pytest

from skat.table.records import Actor
from skat.table.service import TableService
from skat.web.streams import SourceMessage, StreamEvent
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from skat.web.wakes import AccountTopic, TableTopic
from tests.support.fake_tables import FakeTableStore
from tests.web.support.lobby_scene import DAYS, Scene
from tests.web.support.skat import Skat
from tests.web.support.streams import run_on_a_loop_of_its_own

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


def waits_for(scene, person):
    held = scene.service.tables_held_by(person.account_id)
    return [entry.awaits_you for entry in scene.service.my_tables(person.account_id, held, {}, DAYS)]


def a_seed_where_the_deal_gives_anna_the_turn():
    for seed in count():
        scene = Scene(TableService(FakeTableStore(), random_source=Random(seed)))  # noqa: S311 - a seeded generator repeats the deal
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)
        if waits_for(scene, ANNA) == [True]:
            return seed
    raise AssertionError  # pragma: no cover - the loop returns


@pytest.fixture
def scene():
    seed = a_seed_where_the_deal_gives_anna_the_turn()
    return Scene(TableService(FakeTableStore(), random_source=Random(seed)))  # noqa: S311 - a seeded generator repeats the deal


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


def first_attention(scene, person, table_id):
    async def scenario():
        stream = scene.attention_stream(person, table_id)
        number = await next_attention(stream)
        await stream.aclose()
        return number

    return run_on_a_loop_of_its_own(scenario())


class TestWhatIsCounted:
    def test_a_table_that_waits_for_the_person_counts_one_at_the_table_he_sits_at_alone(self, scene):
        deal_at_a_table_of_three(scene)
        solo = scene.open_table(ANNA)

        assert first_attention(scene, ANNA, solo) == "1"

    def test_the_table_the_stream_belongs_to_is_not_counted(self, scene):
        table_id = deal_at_a_table_of_three(scene)

        assert first_attention(scene, ANNA, table_id) == "0"

    @pytest.mark.parametrize("person", [BEN, CLEO, DORA], ids=["another seat", "a third seat", "no chair"])
    def test_a_table_that_waits_for_another_member_never_counts_for_him(self, scene, person):
        deal_at_a_table_of_three(scene)
        elsewhere = scene.open_table(DORA)

        assert first_attention(scene, person, elsewhere) == "0"

    def test_a_person_without_a_chair_at_the_table_he_watches_gets_the_count_of_his_own_tables(self, scene):
        deal_at_a_table_of_three(scene)
        watched = scene.open_table(DORA)

        assert first_attention(scene, ANNA, watched) == "1"

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


class TestTheRoute:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def test_the_table_stream_sends_the_view_unnamed_and_then_the_count_as_attention(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=headers) as answer:
            lines = answer.iter_lines()
            read = [next(lines) for _ in range(5)]
            answer.close()

        assert (read[0].startswith("data: {"), read[1:]) == (True, ["", "event: attention", "data: 0", ""])

    def test_of_three_members_at_a_dealt_table_exactly_the_one_it_waits_for_gets_a_one_at_his_other_table(self, skat):
        people = [skat.member() for _ in range(3)]
        skat.client.cookies.clear()
        dealt = skat.create(people[0][0]).json()["id"]
        skat.sit(people[1][0], dealt, 2)
        skat.sit(people[2][0], dealt, 3)
        elsewhere = [
            skat.create(headers, command_id=f"solo-table-{number}").json()["id"]
            for number, (headers, _) in enumerate(people)
        ]
        counts = []

        for (headers, _), table_id in zip(people, elsewhere, strict=True):
            skat.client.cookies.clear()
            with skat.client.stream("GET", self.events(table_id), headers=headers) as answer:
                lines = answer.iter_lines()
                read = [next(lines) for _ in range(4)]
                answer.close()
            counts.append(read[3].removeprefix("data: "))

        assert sorted(counts) == ["0", "0", "1"]
