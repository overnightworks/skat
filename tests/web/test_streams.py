import asyncio
import json
from datetime import timedelta

import pytest

from skat.table.records import Actor, SitDown, StandUp, TableId
from skat.table.service import TableService
from skat.web.presence import Presence
from skat.web.stream_holder import StreamHolder
from skat.web.streams import IDLE_HEARTBEAT
from tests.support.fake_tables import FakeTableStore
from tests.support.idle_presence import (
    idle_agent_lease,
    idle_empty_table,
    idle_end_answers,
    idle_hold,
    idle_next_deal,
    idle_presence,
    idle_wakes,
)
from tests.support.in_memory_leases import InMemoryLeases
from tests.support.signed_in import cookie_header, seed_member
from tests.web.support.skat import FETCH, UNKNOWN_ID, Skat, unnamed_lines
from tests.web.support.streams import (
    ALLOWED_SECONDS,
    NO_HEARTBEAT_SECONDS,
    OPENER,
    SHORT_HEARTBEAT_SECONDS,
    VISITOR,
    Admission,
    EventsRoute,
    next_view,
    opened_table_id,
    reader,
    run_on_a_loop_of_its_own,
    stream_of,
)

IDLE_HEARTBEATS = 3


@pytest.fixture
def service():
    return TableService(FakeTableStore(), new_table_id=lambda: TableId("1" * 32))


table_id = pytest.fixture(name="table_id")(opened_table_id)


async def idle_heartbeats_through(stream):
    """Takes the next items of a stream with nothing changed, one per heartbeat; these are the items it yielded."""
    async with asyncio.timeout(ALLOWED_SECONDS):
        return [await anext(stream) for _ in range(IDLE_HEARTBEATS)]


class TestTableViews:
    def test_the_first_view_is_the_full_view_and_a_change_brings_a_fresh_one_at_the_same_version(
        self, service, table_id
    ):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id)
            first = await next_view(stream)
            visitor = await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            joined = await next_view(stream)
            await presence.close(visitor)
            left = await next_view(stream)
            await stream.aclose()
            return first, joined, left, presence

        first, joined, left, presence = run_on_a_loop_of_its_own(scenario())

        assert [(view.watchers, view.version) for view in (first, joined, left)] == [(0, 1), (1, 1), (0, 1)]
        assert run_on_a_loop_of_its_own(presence.connected(table_id)) == frozenset()

    def test_a_roster_that_cannot_be_read_ends_the_stream_with_the_failure_and_ends_its_lease(self, service, table_id):
        leases = InMemoryLeases()
        unreachable = ConnectionError("redis is unreachable")

        async def scenario():
            presence = idle_presence(leases=leases)
            stream = stream_of(presence, service, OPENER, table_id)
            await next_view(stream)
            await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            leases.reading_fails = [unreachable]
            with pytest.raises(ConnectionError):
                await next_view(stream)

        run_on_a_loop_of_its_own(scenario())

        assert [StreamHolder.parse(holder).account_id for holder in leases.holders] == [VISITOR.account_id]

    def test_an_unsettled_roster_is_good_enough_for_a_view(self, service, table_id):
        leases = InMemoryLeases()
        leases.settled = False

        async def scenario():
            return await next_view(stream_of(idle_presence(leases=leases), service, OPENER, table_id))

        assert run_on_a_loop_of_its_own(scenario()).watchers == 0

    def test_the_stream_registers_before_it_reads_so_a_change_during_the_read_is_not_lost(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            read_view = reader(service, table_id)
            reads = []

            async def read_while_another_connects(actor, connected):
                reads.append(connected)
                if len(reads) == 1:
                    await presence.subscribe(table_id, "late", lambda: None)
                return await read_view(actor, connected)

            stream = stream_of(presence, service, VISITOR, table_id, read_view=read_while_another_connects)
            first = await next_view(stream)
            second = await next_view(stream)
            await stream.aclose()
            return first, second

        first, second = run_on_a_loop_of_its_own(scenario())

        assert (first.watchers, second.watchers) == (1, 2)

    def test_a_seated_member_shows_away_on_every_other_stream_once_all_tabs_close_and_present_when_one_returns(
        self, service, table_id
    ):
        sit = SitDown("command-2", table_id, 2)
        service.sit(VISITOR, sit, frozenset())

        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id)
            first = await next_view(stream)
            first_tab = await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            second_tab = await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            present = await next_view(stream)
            await presence.close(first_tab)
            await presence.close(second_tab)
            away = await next_view(stream)
            await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            back = await next_view(stream)
            await stream.aclose()
            return first, present, away, back

        views = run_on_a_loop_of_its_own(scenario())

        assert [[chair.is_away for chair in view.chairs] for view in views] == [
            [False, True, False],
            [False, False, False],
            [False, True, False],
            [False, False, False],
        ]
        assert {view.version for view in views} == {2}

    def test_a_change_between_the_registration_and_the_first_read_is_in_the_first_view(self, service, table_id):
        class ConnectsAnotherRightAfterRegistering(Presence):
            async def subscribe(self, table, account, wake):
                subscription = await super().subscribe(table, account, wake)
                if account == VISITOR.account_id:
                    await super().subscribe(table, "late", lambda: None)
                return subscription

        async def scenario():
            presence = ConnectsAnotherRightAfterRegistering(
                idle_hold(),
                idle_next_deal(),
                idle_empty_table(),
                idle_agent_lease(),
                idle_wakes(),
                InMemoryLeases(),
                idle_end_answers(),
            )
            stream = stream_of(presence, service, VISITOR, table_id)
            first = await next_view(stream)
            await stream.aclose()
            return first

        assert run_on_a_loop_of_its_own(scenario()).watchers == 2

    def test_each_stream_gets_the_view_built_for_its_own_account(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            opener_stream = stream_of(presence, service, OPENER, table_id)
            visitor_stream = stream_of(presence, service, VISITOR, table_id)
            views = await next_view(opener_stream), await next_view(visitor_stream)
            await opener_stream.aclose()
            await visitor_stream.aclose()
            return views

        opener_view, visitor_view = run_on_a_loop_of_its_own(scenario())

        assert [chair.is_mine for chair in opener_view.chairs] == [True, False, False]
        assert [chair.is_mine for chair in visitor_view.chairs] == [False, False, False]

    def test_a_stalled_stream_delays_nobody_and_catches_up_with_one_fresh_view(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stalled = stream_of(presence, service, OPENER, table_id)
            await next_view(stalled)
            quick = stream_of(presence, service, VISITOR, table_id)
            await next_view(quick)
            seen_by_quick = []
            for number in range(5):
                guest = await presence.subscribe(table_id, f"guest-{number}", lambda: None)
                seen_by_quick.append((await next_view(quick)).watchers)
                await presence.close(guest)
                await next_view(quick)
            caught_up = await next_view(stalled)
            await stalled.aclose()
            await quick.aclose()
            return seen_by_quick, caught_up

        seen_by_quick, caught_up = run_on_a_loop_of_its_own(scenario())

        assert seen_by_quick == [2] * 5
        assert caught_up.watchers == 1

    def test_a_table_that_vanishes_under_a_stream_is_an_error_that_still_unregisters_it(self, service, table_id):
        async def vanished(_actor, _connected):
            return None

        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id, read_view=vanished)
            with pytest.raises(RuntimeError, match="vanished"):
                await anext(stream)
            return presence

        assert run_on_a_loop_of_its_own(run_on_a_loop_of_its_own(scenario()).connected(table_id)) == frozenset()


class TestLostNotification:
    def test_a_write_whose_wake_is_lost_reaches_the_stream_with_the_next_heartbeat(self, service, table_id):
        async def scenario():
            stream = stream_of(idle_presence(), service, OPENER, table_id, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
            first = await next_view(stream)
            service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())
            recovered = await next_view(stream)
            service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())
            stood = await next_view(stream)
            await stream.aclose()
            return first, recovered, stood

        first, recovered, stood = run_on_a_loop_of_its_own(scenario())

        assert [
            (view.version, [chair.occupant_name for chair in view.chairs]) for view in (first, recovered, stood)
        ] == [
            (1, ["Anna", None, None]),
            (2, ["Anna", "Ben", None]),
            (3, ["Anna", None, None]),
        ]


class TestReadmission:
    def test_a_refusal_before_the_first_view_ends_the_stream_without_a_view(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id, admit=Admission(False))
            return [view async for view in stream], presence

        views, presence = run_on_a_loop_of_its_own(scenario())

        assert views == []
        assert run_on_a_loop_of_its_own(presence.connected(table_id)) == frozenset()

    def test_a_refusal_at_a_change_ends_the_stream_with_nothing_more_sent(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id, admit=Admission(True, True, False))
            first = await next_view(stream)
            visitor = await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            second = await next_view(stream)
            await presence.close(visitor)
            with pytest.raises(StopAsyncIteration):
                await next_view(stream)
            return first, second, presence

        first, second, presence = run_on_a_loop_of_its_own(scenario())

        assert (first.watchers, second.watchers) == (0, 1)
        assert run_on_a_loop_of_its_own(presence.connected(table_id)) == frozenset()

    def test_an_idle_heartbeat_admits_again_and_sends_no_view(self, service, table_id):
        async def scenario():
            admission = Admission()
            stream = stream_of(
                idle_presence(), service, OPENER, table_id, admit=admission, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS
            )
            await next_view(stream)
            marks = await idle_heartbeats_through(stream)
            return marks, admission.asked

        marks, asked = run_on_a_loop_of_its_own(scenario())

        assert marks == [IDLE_HEARTBEAT] * IDLE_HEARTBEATS
        assert asked == IDLE_HEARTBEATS + 1

    def test_a_refusal_at_an_idle_heartbeat_ends_the_stream(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(
                presence,
                service,
                OPENER,
                table_id,
                admit=Admission(True, False),
                heartbeat_seconds=SHORT_HEARTBEAT_SECONDS,
            )
            await next_view(stream)
            with pytest.raises(StopAsyncIteration):
                await next_view(stream)
            return presence

        assert run_on_a_loop_of_its_own(run_on_a_loop_of_its_own(scenario()).connected(table_id)) == frozenset()

    def test_a_change_that_lands_during_a_heartbeat_sends_exactly_one_view(self, service, table_id):
        async def scenario():
            presence = idle_presence()

            class ChangesWhileAdmitting(Admission):
                async def __call__(self):
                    if self.asked == 1:
                        await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
                    return await super().__call__()

            admission = ChangesWhileAdmitting()
            stream = stream_of(
                presence, service, OPENER, table_id, admit=admission, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS
            )
            first = await next_view(stream)
            second = await next_view(stream)
            return first, second, await idle_heartbeats_through(stream)

        first, second, marks = run_on_a_loop_of_its_own(scenario())

        assert (first.watchers, second.watchers) == (0, 1)
        assert marks == [IDLE_HEARTBEAT] * IDLE_HEARTBEATS

    def test_every_view_is_read_as_the_account_the_last_admission_returned(self, service, table_id):
        renamed = Actor(account_id=OPENER.account_id, display_name="Anna Maria")

        async def scenario():
            presence = idle_presence()
            readers = []

            async def read_view(actor, connected):
                readers.append(actor)
                return service.view(actor, table_id, connected)

            admissions = iter([OPENER, renamed])

            async def admit():
                return next(admissions)

            stream = stream_of(presence, service, OPENER, table_id, admit=admit, read_view=read_view)
            await next_view(stream)
            guest = await presence.subscribe(table_id, "guest", lambda: None)
            await next_view(stream)
            await presence.close(guest)
            await stream.aclose()
            return readers

        assert run_on_a_loop_of_its_own(scenario()) == [OPENER, renamed]

    def test_a_store_that_raises_during_admission_ends_the_stream_loudly_and_unregisters_it(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id, admit=Admission(RuntimeError("store down")))
            with pytest.raises(RuntimeError, match="store down"):
                await anext(stream)
            return presence

        assert run_on_a_loop_of_its_own(run_on_a_loop_of_its_own(scenario()).connected(table_id)) == frozenset()

    def test_one_refused_session_ends_only_its_own_stream(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            refused = stream_of(presence, service, OPENER, table_id, admit=Admission(True, False))
            kept = stream_of(presence, service, VISITOR, table_id)
            await next_view(refused)
            await next_view(kept)
            guest = await presence.subscribe(table_id, "guest", lambda: None)
            with pytest.raises(StopAsyncIteration):
                await next_view(refused)
            still_watching = await next_view(kept)
            await presence.close(guest)
            await kept.aclose()
            return still_watching

        assert run_on_a_loop_of_its_own(scenario()).watchers == 2

    def test_stopping_the_presence_ends_every_open_stream_without_a_view(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            streams = [stream_of(presence, service, actor, table_id) for actor in (OPENER, VISITOR)]
            for stream in streams:
                await next_view(stream)
            presence.stop()
            for stream in streams:
                with pytest.raises(StopAsyncIteration):
                    await next_view(stream)
            late = stream_of(presence, service, OPENER, table_id)
            return [view async for view in late], presence

        views, presence = run_on_a_loop_of_its_own(scenario())

        assert views == []
        assert run_on_a_loop_of_its_own(presence.connected(table_id)) == frozenset()


class TestWatchTableAdmission(EventsRoute):
    def test_signed_out_gets_no_stream_and_no_table_data(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.get(self.events(table_id), headers=FETCH)

        assert answer.status_code == 401
        assert table_id not in answer.text

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "%27%3B--", "A" * 32])
    def test_an_unknown_or_malformed_id_is_not_found_and_holds_nothing_open(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.client.get(self.events(table_id), headers=headers)

        assert (answer.status_code, answer.json()) == (404, {"detail": "table not found"})

    def test_a_member_gets_the_full_view_of_the_table_as_the_first_event(self, skat):
        opener_headers, opener = skat.member()
        table = skat.create(opener_headers).json()
        watcher_headers, watcher = skat.member()
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table["id"]), headers=watcher_headers) as answer:
            lines = iter(unnamed_lines(answer.iter_lines()))
            first = next(lines)
            second = next(lines)
            answer.close()

        assert (answer.status_code, answer.headers["content-type"], answer.headers["cache-control"]) == (
            200,
            "text/event-stream; charset=utf-8",
            "no-store",
        )
        event = json.loads(first.removeprefix("data: "))
        assert second == ""
        assert (event["id"], event["version"], event["watchers"]) == (table["id"], 1, 1)
        assert [chair["is_mine"] for chair in event["chairs"]] == [False, False, False]
        assert watcher.id not in first
        assert opener.id not in first
        assert event["hand"] is None
        assert [chair["hand"] for chair in event["chairs"]] == [None, None, None]

    def test_a_probe_of_a_table_stream_registers_no_presence(self, skat):
        opener_headers, _ = skat.member()
        table = skat.create(opener_headers).json()
        watcher_headers, _ = skat.member()
        skat.client.cookies.clear()

        assert skat.client.head(self.events(table["id"]), headers=opener_headers).status_code == 200
        with skat.client.stream("GET", self.events(table["id"]), headers=watcher_headers) as answer:
            first = next(iter(unnamed_lines(answer.iter_lines())))
            answer.close()

        event = json.loads(first.removeprefix("data: "))
        assert ([chair["is_away"] for chair in event["chairs"]], event["watchers"]) == ([True, False, False], 1)

    def test_the_first_event_marks_a_seated_member_without_a_stream_away_and_names_no_account(self, skat):
        opener_headers, opener = skat.member()
        table = skat.create(opener_headers).json()
        watcher_headers, watcher = skat.member()
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table["id"]), headers=watcher_headers) as answer:
            first = next(iter(unnamed_lines(answer.iter_lines())))
            answer.close()

        event = json.loads(first.removeprefix("data: "))
        assert [chair["is_away"] for chair in event["chairs"]] == [True, False, False]
        assert opener.id not in first
        assert watcher.id not in first

    def test_an_idle_stream_writes_a_comment_line_at_each_heartbeat(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        headers, _ = skat.member()
        table = skat.create(headers).json()
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table["id"]), headers=headers) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            after_first = [next(lines) for _ in range(4)]
            answer.close()

        assert first.startswith("data: ")
        assert after_first == ["", ": ", "", ": "]

    def test_a_session_ended_server_side_ends_the_stream_at_the_next_heartbeat(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        headers, member = skat.member()
        table = skat.create(headers).json()
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table["id"]), headers=headers) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            skat.stores.sessions.delete_for_user(member.id)
            rest = list(lines)

        assert first.startswith("data: ")
        assert rest == [""]

    def test_a_session_that_reaches_its_expiry_while_the_stream_is_open_ends_the_stream(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        now = [1_800_000_000.0]
        skat.run_on_clock(now)
        headers, _ = skat.member()
        table = skat.create(headers).json()
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table["id"]), headers=headers) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            now[0] += skat.config.session_lifetime.absolute_max_age_seconds + 1
            rest = list(lines)

        assert first.startswith("data: ")
        assert rest == [""]

    def test_a_revoked_session_ends_every_stream_that_shares_it(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        headers, member = skat.member()
        table = skat.create(headers).json()
        skat.client.cookies.clear()

        with (
            skat.client.stream("GET", self.events(table["id"]), headers=headers) as one_tab,
            skat.client.stream("GET", self.events(table["id"]), headers=headers) as another_tab,
        ):
            tabs = [unnamed_lines(one_tab.iter_lines()), unnamed_lines(another_tab.iter_lines())]
            first_lines = [next(lines) for lines in tabs]
            skat.stores.sessions.delete_for_user(member.id)
            rests = [list(lines) for lines in tabs]

        assert all(line.startswith("data: ") for line in first_lines)
        assert rests == [[""], [""]]

    def test_admitting_a_view_renews_the_session_of_the_open_stream(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=NO_HEARTBEAT_SECONDS)
        seeded = seed_member(skat.stores, skat.config, expires_in=timedelta(hours=1))
        headers = {"cookie": cookie_header(seeded.set_cookie_headers), **FETCH}
        table = skat.create(headers).json()
        skat.client.cookies.clear()
        sessions = skat.stores.sessions

        def expiry():
            return sessions.records_of(seeded.account.id).sessions[0].expires_at

        with skat.client.stream("GET", self.events(table["id"]), headers=headers) as watching:
            lines = unnamed_lines(watching.iter_lines())
            next(lines)
            next(lines)
            opened_with = expiry()
            sessions.touch(seeded.session.id, expires_at=opened_with - timedelta(hours=1))
            # A second member joining is the change whose view the stream admits again for.
            other_headers, _ = skat.member()
            with skat.client.stream("GET", self.events(table["id"]), headers=other_headers) as other:
                other_lines = unnamed_lines(other.iter_lines())
                next(other_lines)
                next(lines)
                next(lines)
            renewed_to = expiry()

        assert renewed_to >= opened_with
