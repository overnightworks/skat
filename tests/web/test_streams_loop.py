import pytest

from skat.table.records import CloseTable, CreateTable, SitDown
from skat.web.streams import IDLE_HEARTBEAT, SourceMessage, StreamEvent, TableSource, stream_messages
from tests.support.fake_tables import in_memory_tables
from tests.support.idle_presence import idle_presence
from tests.web.support.skat import UNKNOWN_ID
from tests.web.support.streams import (
    NO_HEARTBEAT_SECONDS,
    OPENER,
    SHORT_HEARTBEAT_SECONDS,
    VISITOR,
    Admission,
    admitting,
    leased_reader,
    next_item,
    next_view,
    reader,
    run_on_a_loop_of_its_own,
    stream_of,
    version_reader,
)


@pytest.fixture
def service():
    return in_memory_tables()


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-1")).id


class TestStreamLoop:
    def test_a_wake_that_changes_nothing_sends_nothing_and_the_next_item_is_the_heartbeat_marker(
        self, service, table_id
    ):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            await next_view(stream)
            presence.wake_table(table_id)
            item = await next_item(stream)
            await stream.aclose()
            return item

        assert run_on_a_loop_of_its_own(scenario()) == IDLE_HEARTBEAT

    def test_a_wake_of_another_table_reads_nothing_again(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            reads = []
            read_view = reader(service, table_id)

            async def counting(actor, connected):
                reads.append(connected)
                return await read_view(actor, connected)

            stream = stream_of(
                presence,
                service,
                OPENER,
                table_id,
                heartbeat_seconds=SHORT_HEARTBEAT_SECONDS,
                read_view=counting,
            )
            await next_view(stream)
            presence.wake_table(UNKNOWN_ID)
            item = await next_item(stream)
            await stream.aclose()
            return item, len(reads)

        item, reads = run_on_a_loop_of_its_own(scenario())

        assert (item, reads) == (IDLE_HEARTBEAT, 1)

    def test_wakes_that_send_nothing_do_not_starve_the_heartbeat(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            read_view = reader(service, table_id)

            async def waking_itself_on_every_read(actor, connected):
                presence.wake_table(table_id)
                return await read_view(actor, connected)

            stream = stream_of(
                presence,
                service,
                OPENER,
                table_id,
                heartbeat_seconds=SHORT_HEARTBEAT_SECONDS,
                read_view=waking_itself_on_every_read,
            )
            await next_view(stream)
            item = await next_item(stream)
            await stream.aclose()
            return item

        assert run_on_a_loop_of_its_own(scenario()) == IDLE_HEARTBEAT

    def test_a_stop_that_lands_during_an_admission_ends_the_stream_without_a_message(self, service, table_id):
        async def scenario():
            presence = idle_presence()

            class StopsWhileAdmitting(Admission):
                async def __call__(self):
                    if self.asked == 1:
                        presence.stop()
                    return await super().__call__()

            stream = stream_of(presence, service, OPENER, table_id, admit=StopsWhileAdmitting())
            await next_view(stream)
            presence.wake_table(table_id)
            with pytest.raises(StopAsyncIteration):
                await next_item(stream)
            return presence

        assert run_on_a_loop_of_its_own(scenario()).connected(table_id) == frozenset()

    def test_a_source_that_fails_ends_only_its_own_stream(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            read_view = reader(service, table_id)
            reads = []

            async def failing_on_the_second_read(actor, connected):
                reads.append(connected)
                if len(reads) == 2:
                    message = "store down"
                    raise RuntimeError(message)
                return await read_view(actor, connected)

            failing = stream_of(presence, service, OPENER, table_id, read_view=failing_on_the_second_read)
            kept = stream_of(presence, service, VISITOR, table_id)
            await next_view(failing)
            await next_view(kept)
            guest = await presence.subscribe(table_id, "guest", lambda: None)
            with pytest.raises(RuntimeError, match="store down"):
                await next_view(failing)
            still_watching = await next_view(kept)
            presence.unsubscribe(guest)
            await kept.aclose()
            return still_watching, presence

        still_watching, presence = run_on_a_loop_of_its_own(scenario())

        assert still_watching.watchers == 2
        assert presence.connected(table_id) == frozenset()


async def sat_down(service, presence, table_id):
    service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())


async def connected_a_watcher(service, presence, table_id):
    await presence.subscribe(table_id, VISITOR.account_id, lambda: None)


async def started_the_lease_of_a_sitter(service, presence, table_id):
    presence.renew_lease(OPENER.account_id)


async def started_the_lease_of_a_stranger(service, presence, table_id):
    presence.renew_lease(VISITOR.account_id)


async def closed_the_table(service, presence, table_id):
    service.close(OPENER, CloseTable("command-close", table_id))


async def did_nothing(service, presence, table_id):
    pass


class TestTheTableSourceMoves:
    @pytest.mark.parametrize(
        ("happens", "moved"),
        [
            pytest.param(did_nothing, False, id="nothing"),
            pytest.param(sat_down, True, id="a-commit"),
            pytest.param(connected_a_watcher, True, id="a-watcher"),
            pytest.param(started_the_lease_of_a_sitter, True, id="the-lease-of-a-sitter"),
            pytest.param(started_the_lease_of_a_stranger, False, id="the-lease-of-an-account-that-sits-elsewhere"),
            pytest.param(closed_the_table, True, id="the-end"),
        ],
    )
    def test_a_table_source_has_moved_since_its_read_when_the_version_or_who_is_present_changed(
        self, service, table_id, happens, moved
    ):
        async def scenario():
            presence = idle_presence()
            leasing = service.with_leases(presence.live_leases)
            source = TableSource(
                presence,
                reader(leasing, table_id),
                version_reader(leasing, table_id),
                leased_reader(leasing, table_id),
                table_id,
                OPENER.account_id,
            )
            await source.open(lambda: None)
            await source.read(OPENER)
            await happens(service, presence, table_id)
            answer = await source.moved(OPENER)
            source.close()
            return answer

        assert run_on_a_loop_of_its_own(scenario()) is moved


class WholeNumberSource:
    """A source whose state is one number, read as the named event; `wake` is what the loop gave it to call."""

    def __init__(self, event, number=0, fails_to_open=False):
        self.event = event
        self.number = number
        self.fails_to_open = fails_to_open
        self.reads = 0
        self.checks = 0
        self.read_number = None
        self.is_open = False
        self.wake = None

    async def open(self, wake):
        if self.fails_to_open:
            message = "cannot open"
            raise RuntimeError(message)
        self.wake = wake
        self.is_open = True

    async def read(self, actor):
        self.reads += 1
        self.read_number = self.number
        return SourceMessage(str(self.number), event=self.event)

    async def moved(self, actor):
        self.checks += 1
        return self.number != self.read_number

    def close(self):
        self.is_open = False


def stream_of_numbers(*sources, heartbeat_seconds=NO_HEARTBEAT_SECONDS, stopped=lambda: False):
    return stream_messages(sources, admitting(OPENER), stopped, heartbeat_seconds=heartbeat_seconds)


async def next_numbers(stream, count):
    return [(item.event, item.data) for item in [await next_item(stream) for _ in range(count)]]


class TestSeveralSources:
    def test_each_source_sends_its_whole_state_first_in_the_order_the_stream_lists_them(self):
        async def scenario():
            stream = stream_of_numbers(
                WholeNumberSource(StreamEvent.MINE, 4), WholeNumberSource(StreamEvent.ATTENTION, 7)
            )
            first = await next_numbers(stream, 2)
            await stream.aclose()
            return first

        assert run_on_a_loop_of_its_own(scenario()) == [(StreamEvent.MINE, "4"), (StreamEvent.ATTENTION, "7")]

    def test_a_wake_of_one_source_reads_only_that_source(self):
        async def scenario():
            kept = WholeNumberSource(StreamEvent.MINE)
            woken = WholeNumberSource(StreamEvent.ATTENTION)
            stream = stream_of_numbers(kept, woken)
            await next_numbers(stream, 2)
            woken.number = 2
            woken.wake()
            message = await next_item(stream)
            await stream.aclose()
            return message, kept.reads

        message, reads_of_the_kept = run_on_a_loop_of_its_own(scenario())

        assert (message.event, message.data, reads_of_the_kept) == (StreamEvent.ATTENTION, "2", 1)

    def test_a_heartbeat_reads_again_only_the_sources_that_moved_and_sends_what_changed_without_a_wake(self):
        async def scenario():
            quiet = WholeNumberSource(StreamEvent.MINE)
            lost_a_wake = WholeNumberSource(StreamEvent.ATTENTION)
            stream = stream_of_numbers(quiet, lost_a_wake, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            await next_numbers(stream, 2)
            lost_a_wake.number = 5
            message = await next_item(stream)
            await stream.aclose()
            return message, quiet

        message, quiet = run_on_a_loop_of_its_own(scenario())

        assert (message.event, message.data, quiet.reads, quiet.checks > 0) == (StreamEvent.ATTENTION, "5", 1, True)

    def test_a_heartbeat_that_finds_nothing_moved_sends_only_the_comment_line_however_often_it_passes(self):
        async def scenario():
            source = WholeNumberSource(StreamEvent.MINE)
            stream = stream_of_numbers(source, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            await next_numbers(stream, 1)
            beats = [await next_item(stream) for _ in range(3)]
            await stream.aclose()
            return beats, source

        beats, source = run_on_a_loop_of_its_own(scenario())

        assert (beats, source.reads) == ([IDLE_HEARTBEAT] * 3, 1)

    def test_a_woken_source_is_read_without_asking_whether_it_moved(self):
        async def scenario():
            source = WholeNumberSource(StreamEvent.MINE)
            stream = stream_of_numbers(source)
            await next_numbers(stream, 1)
            source.number = 3
            source.wake()
            message = await next_item(stream)
            await stream.aclose()
            return message, source

        message, source = run_on_a_loop_of_its_own(scenario())

        assert (message.data, source.checks) == ("3", 0)

    def test_a_last_message_ends_the_stream_before_the_sources_after_it_are_read(self):
        class Ends(WholeNumberSource):
            async def read(self, actor):
                return SourceMessage("ended", last=True)

        async def scenario():
            later = WholeNumberSource(StreamEvent.ATTENTION)
            stream = stream_of_numbers(Ends(None), later)
            first = await next_item(stream)
            with pytest.raises(StopAsyncIteration):
                await next_item(stream)
            return first, later

        first, later = run_on_a_loop_of_its_own(scenario())

        assert (first.data, later.reads, later.is_open) == ("ended", 0, False)

    def test_a_source_that_cannot_open_closes_the_sources_opened_before_it_and_fails_the_stream(self):
        async def scenario():
            opened = WholeNumberSource(StreamEvent.MINE)
            stream = stream_of_numbers(opened, WholeNumberSource(StreamEvent.ATTENTION, fails_to_open=True))
            with pytest.raises(RuntimeError, match="cannot open"):
                await next_item(stream)
            return opened

        opened = run_on_a_loop_of_its_own(scenario())

        assert (opened.reads, opened.is_open) == (0, False)

    def test_closing_the_stream_closes_every_source(self):
        async def scenario():
            sources = [WholeNumberSource(StreamEvent.MINE), WholeNumberSource(StreamEvent.ATTENTION)]
            stream = stream_of_numbers(*sources)
            await next_numbers(stream, 2)
            await stream.aclose()
            return [source.is_open for source in sources]

        assert run_on_a_loop_of_its_own(scenario()) == [False, False]
