import asyncio
import json
from datetime import timedelta

import pytest

from skat.engine.deal import next_dealer
from skat.table.records import Actor, CreateTable, SitDown, StandUp, TableId
from skat.table.service import TableService
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.presence import Presence
from skat.web.streams import IDLE_HEARTBEAT
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from skat.web.wakes import WakeList
from tests.support.fake_tables import FakeTableStore
from tests.support.idle_presence import (
    idle_agent_lease,
    idle_empty_table,
    idle_hold,
    idle_next_deal,
    idle_presence,
)
from tests.support.payload_cards import CARDS_BY_SEAT, DEALER_SEAT, SKAT_CARDS, cards_in_text, seated_three, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member
from tests.web.support.skat import FETCH, UNKNOWN_ID, Skat, unnamed_lines
from tests.web.support.streams import (
    ALLOWED_SECONDS,
    NO_HEARTBEAT_SECONDS,
    OPENER,
    SHORT_HEARTBEAT_SECONDS,
    VISITOR,
    Admission,
    next_view,
    reader,
    run_on_a_loop_of_its_own,
    stream_of,
)

IDLE_HEARTBEATS = 3
BID_VALUE = 18


@pytest.fixture
def service():
    return TableService(FakeTableStore(), new_table_id=lambda: TableId("1" * 32))


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-1")).id


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
            presence.unsubscribe(visitor)
            left = await next_view(stream)
            await stream.aclose()
            return first, joined, left, presence

        first, joined, left, presence = run_on_a_loop_of_its_own(scenario())

        assert [(view.watchers, view.version) for view in (first, joined, left)] == [(0, 1), (1, 1), (0, 1)]
        assert presence.connected(table_id) == frozenset()

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
            presence.unsubscribe(first_tab)
            presence.unsubscribe(second_tab)
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
                idle_hold(), idle_next_deal(), idle_empty_table(), idle_agent_lease(), WakeList()
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
                presence.unsubscribe(guest)
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

        assert run_on_a_loop_of_its_own(scenario()).connected(table_id) == frozenset()


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
        assert presence.connected(table_id) == frozenset()

    def test_a_refusal_at_a_change_ends_the_stream_with_nothing_more_sent(self, service, table_id):
        async def scenario():
            presence = idle_presence()
            stream = stream_of(presence, service, OPENER, table_id, admit=Admission(True, True, False))
            first = await next_view(stream)
            visitor = await presence.subscribe(table_id, VISITOR.account_id, lambda: None)
            second = await next_view(stream)
            presence.unsubscribe(visitor)
            with pytest.raises(StopAsyncIteration):
                await next_view(stream)
            return first, second, presence

        first, second, presence = run_on_a_loop_of_its_own(scenario())

        assert (first.watchers, second.watchers) == (0, 1)
        assert presence.connected(table_id) == frozenset()

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

        assert run_on_a_loop_of_its_own(scenario()).connected(table_id) == frozenset()

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
            presence.unsubscribe(guest)
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

        assert run_on_a_loop_of_its_own(scenario()).connected(table_id) == frozenset()

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
            presence.unsubscribe(guest)
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
        assert presence.connected(table_id) == frozenset()


class TestWatchTableAdmission:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

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


class TestHandOnTheStream:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def first_message(self, skat, headers, table_id):
        with skat.client.stream("GET", self.events(table_id), headers=headers) as answer:
            first = next(unnamed_lines(answer.iter_lines()))
            answer.close()
        return first

    @pytest.mark.parametrize(
        ("who", "own"),
        [
            pytest.param(0, CARDS_BY_SEAT[1], id="anna"),
            pytest.param(1, CARDS_BY_SEAT[2], id="ben"),
            pytest.param(2, CARDS_BY_SEAT[3], id="cleo"),
            pytest.param(3, (), id="dora-without-a-chair"),
        ],
    )
    def test_the_first_message_and_the_one_a_watcher_wakes_carry_exactly_the_viewers_own_cards(self, skat, who, own):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=people[who][0]) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            next(lines)
            arriving_headers, _ = skat.member()
            skat.client.cookies.clear()
            with skat.client.stream("GET", self.events(table_id), headers=arriving_headers) as arriving:
                arriving_lines = unnamed_lines(arriving.iter_lines())
                next(arriving_lines)
                woken = next(lines)

        assert cards_in_text(first) == wire_cards(own)
        assert cards_in_text(woken) == wire_cards(own)

    def test_one_account_on_two_devices_gets_its_own_cards_on_both(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        anna_headers, anna = people[0]
        laptop_session = seed_member(skat.stores, skat.config, account=anna)
        laptop_headers = {"cookie": cookie_header(laptop_session.set_cookie_headers), **FETCH}

        with (
            skat.client.stream("GET", self.events(table_id), headers=anna_headers) as phone,
            skat.client.stream("GET", self.events(table_id), headers=laptop_headers) as laptop,
        ):
            firsts = [next(unnamed_lines(phone.iter_lines())), next(unnamed_lines(laptop.iter_lines()))]

        assert [cards_in_text(first) for first in firsts] == [wire_cards(CARDS_BY_SEAT[1])] * 2

    def test_an_accepted_step_sends_each_open_stream_a_fresh_snapshot_with_the_new_version_and_only_its_own_cards(
        self, skat
    ):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        middlehand_headers, rearhand_headers = people[0][0], people[1][0]

        with skat.client.stream("GET", self.events(table_id), headers=middlehand_headers) as first_stream:
            first_lines = unnamed_lines(first_stream.iter_lines())
            opened = json.loads(next(first_lines).removeprefix("data: "))
            next(first_lines)
            with skat.client.stream("GET", self.events(table_id), headers=rearhand_headers) as second_stream:
                second_lines = unnamed_lines(second_stream.iter_lines())
                next(second_lines)
                next(second_lines)
                # The second stream joining is a change the first stream hears about before the step.
                next(first_lines)
                next(first_lines)
                skat.client.cookies.clear()
                answer = skat.client.post(
                    f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_BID_SUFFIX}",
                    json={"command_id": "step-0001", "version": opened["version"], "value": BID_VALUE},
                    headers={"origin": TEST_PUBLIC_ORIGIN, **middlehand_headers},
                )
                first_fresh, second_fresh = next(first_lines), next(second_lines)

        assert answer.status_code == 200
        fresh = json.loads(first_fresh.removeprefix("data: "))
        assert fresh["version"] == opened["version"] + 1
        assert set(fresh) == {
            "id",
            "version",
            "chairs",
            "watchers",
            "hand",
            "passed_in",
            "result",
            "series",
            "options",
            "bock",
            "ended",
            "opened_by_me",
        }
        assert json.loads(second_fresh.removeprefix("data: "))["version"] == opened["version"] + 1
        assert cards_in_text(first_fresh) == wire_cards(CARDS_BY_SEAT[1])
        assert cards_in_text(second_fresh) == wire_cards(CARDS_BY_SEAT[2])
        for message in (first_fresh, second_fresh):
            auction = json.loads(message.removeprefix("data: "))["hand"]["auction"]
            assert auction["standing"] == BID_VALUE
            assert auction["awaiting"] == "answer"
            assert [word["value"] for word in auction["words"]] == [BID_VALUE]

    def test_a_stream_opened_mid_auction_starts_from_the_full_auction(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        middlehand_headers, rearhand_headers = people[0][0], people[1][0]
        version = json.loads(self.first_message(skat, middlehand_headers, table_id).removeprefix("data: "))["version"]
        skat.client.cookies.clear()
        skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_BID_SUFFIX}",
            json={"command_id": "step-0001", "version": version, "value": BID_VALUE},
            headers={"origin": TEST_PUBLIC_ORIGIN, **middlehand_headers},
        )
        skat.client.cookies.clear()

        opened = json.loads(self.first_message(skat, rearhand_headers, table_id).removeprefix("data: "))

        assert opened["hand"]["auction"]["standing"] == BID_VALUE
        assert [word["action"] for word in opened["hand"]["auction"]["words"]] == ["bid"]

    def test_the_third_pass_sends_every_stream_a_fresh_snapshot_that_says_passed_in_and_names_no_card(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        middlehand, rearhand, forehand, watcher = (person[0] for person in people)

        with skat.client.stream("GET", self.events(table_id), headers=watcher) as stream:
            lines = unnamed_lines(stream.iter_lines())
            messages = (line for line in lines if line.startswith("data: "))
            opened = json.loads(next(messages).removeprefix("data: "))
            skat.client.cookies.clear()
            for offset, headers in enumerate((middlehand, rearhand, forehand)):
                answer = skat.client.post(
                    f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
                    json={"command_id": f"step-{offset:04d}", "version": opened["version"] + offset},
                    headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
                )
                assert answer.status_code == 200, answer.text
            final = next(
                line for line in messages if json.loads(line.removeprefix("data: "))["version"] == opened["version"] + 3
            )

        payload = json.loads(final.removeprefix("data: "))
        assert payload["hand"] is None
        assert payload["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}
        assert cards_in_text(final) == set()

    def test_a_stream_opened_after_the_hand_ended_says_passed_in_and_names_no_card(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        for offset, (headers, _) in enumerate(people[:3]):
            record = skat.store.tables[table_id]
            skat.client.post(
                f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
                json={"command_id": f"step-{offset:04d}", "version": record.version},
                headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
            )
        skat.client.cookies.clear()

        first = self.first_message(skat, people[0][0], table_id)

        assert json.loads(first.removeprefix("data: "))["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}
        assert cards_in_text(first) == set()

    def test_an_accepted_declaring_step_sends_the_declarer_a_fresh_snapshot_with_the_twelve_cards(self, skat):
        table_id, people = seated_three(skat)
        declarer_headers, rearhand_headers, forehand_headers = people[0][0], people[1][0], people[2][0]
        for command_id, headers, suffix, fields in [
            ("auction-1", declarer_headers, TABLE_AUCTION_BID_SUFFIX, {"value": 18}),
            ("auction-2", forehand_headers, TABLE_AUCTION_PASS_SUFFIX, {}),
            ("auction-3", rearhand_headers, TABLE_AUCTION_PASS_SUFFIX, {}),
        ]:
            version = skat.store.tables[table_id].version
            bid = skat.client.post(
                f"{TABLES_PATH}/{table_id}{suffix}",
                json={"command_id": command_id, "version": version, **fields},
                headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
            )
            assert bid.status_code == 200, bid.text
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=declarer_headers) as stream:
            lines = unnamed_lines(stream.iter_lines())
            opened = json.loads(next(lines).removeprefix("data: "))
            next(lines)
            skat.client.cookies.clear()
            answer = skat.client.post(
                f"{TABLES_PATH}/{table_id}{TABLE_DECLARING_TAKE_SUFFIX}",
                json={"command_id": "step-0001", "version": opened["version"]},
                headers={"origin": TEST_PUBLIC_ORIGIN, **declarer_headers},
            )
            fresh_line = next(lines)

        assert answer.status_code == 200
        fresh = json.loads(fresh_line.removeprefix("data: "))
        assert fresh["version"] == opened["version"] + 1
        assert set(fresh) == set(opened)
        assert cards_in_text(fresh_line) == wire_cards((*CARDS_BY_SEAT[1], *SKAT_CARDS))
        assert fresh["hand"]["skat_count"] == 0

    def test_a_stream_opened_after_the_last_one_dropped_starts_from_the_full_current_hand(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        anna_headers, _ = people[0]
        self.first_message(skat, anna_headers, table_id)

        again = self.first_message(skat, anna_headers, table_id)

        assert cards_in_text(again) == wire_cards(CARDS_BY_SEAT[1])

    def test_a_revoked_session_gets_no_card_after_the_revocation_and_a_401_on_its_next_read(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        table_id, people = seated_three(skat)
        anna_headers, anna = people[0]
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=anna_headers) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            skat.stores.sessions.delete_for_user(anna.id)
            rest = list(lines)
        next_read = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=anna_headers)

        assert cards_in_text(first) == wire_cards(CARDS_BY_SEAT[1])
        assert rest == [""]
        assert next_read.status_code == 401
        assert cards_in_text(next_read.text) == set()
