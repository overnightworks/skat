"""An idle lobby heartbeat reads a source again only when the source says it moved."""

import pytest

from skat.table.records import CloseTable, CreateTable, SitDown
from skat.table.service import TableService
from skat.web.streams import IDLE_HEARTBEAT, StreamEvent, stream_messages
from tests.support.fake_tables import FakeTableStore
from tests.web.support.lobby_scene import ANNA, BEN, CLEO, Scene, ids_of, next_mine, next_open
from tests.web.support.streams import (
    SHORT_HEARTBEAT_SECONDS,
    admitting,
    next_item,
    run_on_a_loop_of_its_own,
)


class CountingFullReads(TableService):
    """A service that counts the full reads of the lobby's lists: the reads of every table's record."""

    def __init__(self, store):
        super().__init__(store)
        self.mine_reads = 0
        self.open_reads = 0

    def my_tables(self, *arguments):
        self.mine_reads += 1
        return super().my_tables(*arguments)

    def open_tables(self, *arguments):
        self.open_reads += 1
        return super().open_tables(*arguments)


class TestTheIdleHeartbeat:
    def test_a_heartbeat_with_nothing_moved_sends_only_the_comment_line_and_reads_no_table_again(self):
        scene = Scene(CountingFullReads(FakeTableStore()))
        scene.sit(BEN, scene.open_table(ANNA), 2)
        scene.open_table(CLEO)

        async def scenario():
            stream = stream_messages(
                [scene.source(BEN), scene.open_source(BEN)],
                admitting(BEN),
                lambda: scene.presence.stopped,
                heartbeat_seconds=SHORT_HEARTBEAT_SECONDS,
            )
            firsts = [await next_item(stream), await next_item(stream)]
            beats = [await next_item(stream) for _ in range(3)]
            await stream.aclose()
            return firsts, beats

        firsts, beats = run_on_a_loop_of_its_own(scenario())

        assert [item.event for item in firsts] == [StreamEvent.MINE, StreamEvent.OPEN]
        assert (beats, scene.service.mine_reads, scene.service.open_reads) == ([IDLE_HEARTBEAT] * 3, 1, 1)

    def test_a_commit_at_a_held_table_that_no_wake_announced_arrives_with_the_heartbeat(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.sit(BEN, table_id, 2)

        async def scenario():
            stream = scene.stream(BEN, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            before = await next_mine(stream)
            scene.service.sit(CLEO, SitDown("sit-cleo", table_id, 3), frozenset())
            after = await next_mine(stream)
            await stream.aclose()
            return before, after

        before, after = run_on_a_loop_of_its_own(scenario())

        assert [[chair["occupant_name"] for chair in tables[0]["chairs"]] for tables in (before, after)] == [
            ["Anna", "Ben", None],
            ["Anna", "Ben", "Cleo"],
        ]

    def test_a_table_a_stranger_opens_without_a_wake_arrives_in_the_open_list_with_the_heartbeat(self):
        scene = Scene()

        async def scenario():
            stream = scene.open_stream(BEN, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            before = await next_open(stream)
            opened = scene.service.create(CLEO, CreateTable(command_id="open-without-a-wake")).id
            after = await next_open(stream)
            await stream.aclose()
            return before, after, opened

        before, after, opened = run_on_a_loop_of_its_own(scenario())

        assert (before, ids_of(after)) == ([], [opened])


def mine_of_anna(scene):
    return scene.source(ANNA)


def open_list_of_cleo(scene):
    return scene.open_source(CLEO)


async def ben_sits(scene, table_id):
    scene.service.sit(BEN, SitDown("sit-ben", table_id, 2), frozenset())


async def ben_watches(scene, table_id):
    await scene.presence.subscribe(table_id, BEN.account_id, lambda: None)


async def ben_opens_a_table(scene, table_id):
    scene.service.create(BEN, CreateTable(command_id="open-ben"))


async def the_lease_of_a_sitter_starts(scene, table_id):
    scene.presence.renew_lease(ANNA.account_id)


async def the_lease_of_a_stranger_starts(scene, table_id):
    scene.presence.renew_lease(BEN.account_id)


async def anna_closes_the_table(scene, table_id):
    scene.service.close(ANNA, CloseTable("close-anna", table_id))


async def nothing_happens(scene, table_id):
    pass


class TestWhatMovesASource:
    @pytest.mark.parametrize(
        ("source_of", "happens", "moved"),
        [
            pytest.param(mine_of_anna, nothing_happens, False, id="mine-nothing"),
            pytest.param(mine_of_anna, ben_sits, True, id="mine-a-commit-at-a-held-table"),
            pytest.param(mine_of_anna, ben_watches, True, id="mine-a-watcher-at-a-held-table"),
            pytest.param(mine_of_anna, the_lease_of_a_sitter_starts, True, id="mine-the-lease-of-a-sitter"),
            pytest.param(
                mine_of_anna, the_lease_of_a_stranger_starts, False, id="mine-the-lease-of-an-unseated-account"
            ),
            pytest.param(mine_of_anna, anna_closes_the_table, True, id="mine-a-held-table-ends"),
            pytest.param(mine_of_anna, ben_opens_a_table, False, id="mine-a-table-of-a-stranger"),
            pytest.param(open_list_of_cleo, nothing_happens, False, id="open-nothing"),
            pytest.param(open_list_of_cleo, ben_sits, True, id="open-a-commit-at-a-listed-table"),
            pytest.param(open_list_of_cleo, ben_watches, True, id="open-a-watcher-at-a-listed-table"),
            pytest.param(open_list_of_cleo, ben_opens_a_table, True, id="open-a-table-opened"),
            pytest.param(open_list_of_cleo, the_lease_of_a_sitter_starts, True, id="open-the-lease-of-a-sitter"),
            pytest.param(
                open_list_of_cleo, the_lease_of_a_stranger_starts, False, id="open-the-lease-of-an-unseated-account"
            ),
            pytest.param(open_list_of_cleo, anna_closes_the_table, True, id="open-a-listed-table-ends"),
        ],
    )
    def test_a_source_has_moved_when_the_versions_of_its_tables_or_who_is_present_there_changed(
        self, source_of, happens, moved
    ):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            source = source_of(scene)
            await source.open(lambda: None)
            await source.read(ANNA)
            await happens(scene, table_id)
            answer = await source.moved(ANNA)
            source.close()
            return answer

        assert run_on_a_loop_of_its_own(scenario()) is moved
