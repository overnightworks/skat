"""A seat the table waits for is asked again: the agent's view gets a new revision at each deadline, a pulse on its
view's URI wakes the agent to read it, and the table's version never moves for an ask.
"""

import asyncio
import threading
from contextlib import nullcontext
from dataclasses import replace
from functools import partial
from datetime import timedelta
from types import SimpleNamespace

import pytest
from agents.mcp_server import ResourceChanges
from agents.member import LEASE_SECONDS, STANDING_URI
from agents.tools import Principal
from starlette.concurrency import run_in_threadpool
from structlog.testing import capture_logs

from skat.engine.deal import Position
from skat.host.app import _empty_table
from skat.table.asking import ASK_AGAIN_AFTER, ASKS_AGAIN, revision_of
from skat.table.member_place import InvitationRequest
from skat.table.records import EndedTable, EndReason, Series, TableId
from skat.web.mcp import AUCTION_BID_TOOL, AUCTION_HOLD_TOOL, token_carries_agent_facts
from skat.web.member_place import AskClock, MemberStandings
from skat.web.ready import TABLE_READY_SUFFIX
from tests.support.payload_cards import with_known_deal
from tests.support.played_game import after_the_first_game
from tests.web.support.agent import SUBJECT, Agent, person_posts, view_uri_of
from tests.web.support.sdk_agent import SdkAgent
from tests.web.support.skat import FakeTime, Skat, stored

MIDDLEHAND = Position.MIDDLEHAND
OTHER_AGENT_SUBJECT = "other-agent-subject"
TABLE = "a-table"
ACCOUNT = "an-account"
OTHER_ACCOUNT = "another-account"
OWNER = "the-agents-owner"
INVITATION_SECONDS = 600


class Moments:
    """A clock the test sets."""

    def __init__(self):
        self.now = 500.0

    def __call__(self):
        return self.now


class TestTheWaitIsKeptPerTableAndVersion:
    @pytest.fixture
    def moments(self):
        return Moments()

    @pytest.fixture
    def clock(self, moments):
        return AskClock(moments)

    def test_the_first_sight_of_a_version_starts_its_wait_now(self, clock, moments):
        assert clock.see(TABLE, 5) == moments.now

    def test_a_later_sight_of_the_same_version_keeps_the_earliest_time(self, clock, moments):
        first = moments.now
        clock.see(TABLE, 5)
        moments.now += 30

        assert clock.see(TABLE, 5) == first

    def test_a_lower_version_changes_nothing_and_has_no_wait_of_its_own(self, clock, moments):
        clock.see(TABLE, 6)
        moments.now += 30

        assert clock.see(TABLE, 5) is None
        assert (clock.is_current(TABLE, 6), clock.is_current(TABLE, 5)) == (True, False)

    def test_each_table_has_its_own_entry(self, clock, moments):
        clock.see(TABLE, 6)
        moments.now += 30

        assert clock.see("another-table", 5) == moments.now

    def test_the_pulses_of_a_version_are_claimed_once_for_each_account(self, clock):
        clock.see(TABLE, 5)

        claims = [clock.claim_pulses(TABLE, 5, account) for account in (ACCOUNT, ACCOUNT, OTHER_ACCOUNT)]

        assert claims == [True, False, True]

    def test_a_new_version_can_be_claimed_again(self, clock):
        clock.see(TABLE, 5)
        clock.claim_pulses(TABLE, 5, ACCOUNT)
        clock.see(TABLE, 6)

        assert clock.claim_pulses(TABLE, 6, ACCOUNT) is True

    def test_a_version_that_is_not_the_entrys_cannot_be_claimed(self, clock):
        clock.see(TABLE, 6)

        assert clock.claim_pulses(TABLE, 5, ACCOUNT) is False

    def test_a_dropped_table_starts_afresh(self, clock, moments):
        clock.see(TABLE, 6)
        clock.drop(TABLE)
        moments.now += 30

        assert (clock.is_current(TABLE, 6), clock.see(TABLE, 5)) == (False, moments.now)

    def test_dropping_a_table_without_an_entry_does_nothing(self, clock):
        clock.drop(TABLE)

        assert clock.is_current(TABLE, 1) is False

    def test_a_table_dropped_while_it_is_read_gets_no_entry_from_the_read(self, clock):
        with clock.reading(TABLE):
            clock.drop(TABLE)

            assert clock.see(TABLE, 6) is None

        assert clock.is_current(TABLE, 6) is False

    def test_a_table_dropped_while_two_reads_run_gets_no_entry_after_the_first_of_them_ended(self, clock):
        with clock.reading(TABLE):
            with clock.reading(TABLE):
                clock.drop(TABLE)

            assert clock.see(TABLE, 6) is None


class RecordedChanges(ResourceChanges):
    """The changes the app tells, as (account, uri) in the order told; set `failure` and each one raises it."""

    def __init__(self):
        super().__init__()
        self.told = []
        self.failure = None

    def changed(self, recipient, uri):
        self.told.append((recipient.sub, uri))
        if self.failure is not None:
            raise self.failure
        super().changed(recipient, uri)


@pytest.fixture
def changes():
    return RecordedChanges()


@pytest.fixture
def skat(hold, issuer, time, changes):
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
        resource_changes=changes,
    )
    with skat.client:
        yield skat


@pytest.fixture
def sdk(skat, issuer):
    """The seated agent as a runner connects: through the SDK's client."""
    return SdkAgent(skat, issuer)


@pytest.fixture
def pulses(changes):
    """Every change the app told, as (account, uri), in the order told."""
    return changes.told


def account_of(skat, agent):
    return skat.stores.accounts.get(agent.subject).id


def wait(skat, time, seconds):
    skat.client.portal.call(time.advance, seconds)


def a_result_stands(table):
    """The agent's table after a played game, the result waiting for each seat that has not continued."""
    table.declared_hand_game()
    table.skat.store.tables[table.table_id] = replace(after_the_first_game(table.record), series=Series(36, 1))
    table.skat.client.cookies.clear()
    return table


class TestASeatTheTableWaitsForIsAskedAgain:
    def test_each_deadline_raises_the_revision_by_one_and_pulses_the_agent_until_the_last_ask(
        self, skat, time, agent, middlehand_auction, pulses
    ):
        table_id = middlehand_auction.table_id
        first = agent.view(table_id)
        version = first["state"]["version"]
        pulses.clear()

        revisions = []
        for _ in range(ASKS_AGAIN):
            wait(skat, time, ASK_AGAIN_AFTER)
            revisions.append(agent.view(table_id))
        wait(skat, time, 10 * ASK_AGAIN_AFTER)
        after_the_last = agent.view(table_id)

        assert first["revision"] == revision_of(version, 0)
        assert [view["revision"] for view in revisions] == [revision_of(version, asks) for asks in (1, 2)]
        assert after_the_last["revision"] == revision_of(version, ASKS_AGAIN)
        assert pulses == [(account_of(skat, agent), view_uri_of(table_id))] * ASKS_AGAIN
        assert [(view["awaits_you"], view["state"]) for view in (*revisions, after_the_last)] == [
            (True, first["state"])
        ] * (ASKS_AGAIN + 1)

    def test_a_seat_the_table_does_not_wait_for_keeps_its_revision_and_is_not_pulsed(
        self, skat, time, agent, forehand_auction, pulses
    ):
        table_id = forehand_auction.table_id
        first = agent.view(table_id)
        pulses.clear()

        wait(skat, time, 10 * ASK_AGAIN_AFTER)

        assert (first["awaits_you"], agent.view(table_id)["revision"], pulses) == (
            False,
            revision_of(first["state"]["version"], 0),
            [],
        )

    def test_an_act_of_the_seat_before_the_deadline_starts_the_new_version_afresh_and_the_old_pulse_tells_nobody(
        self, skat, time, agent, middlehand_auction, pulses
    ):
        table = middlehand_auction
        agent.view(table.table_id)
        wait(skat, time, ASK_AGAIN_AFTER - 1)
        assert not agent.take_step(AUCTION_BID_TOOL, table, command_id="agent-bid", value=18).is_error
        moved = agent.view(table.table_id)
        pulses.clear()

        wait(skat, time, 1)

        assert (moved["revision"], pulses) == (revision_of(table.record.version, 0), [])

    def test_an_act_of_the_seat_before_the_deadline_with_no_read_after_it_leaves_the_old_pulse_telling_nobody(
        self, skat, time, agent, middlehand_auction, pulses
    ):
        table = middlehand_auction
        agent.view(table.table_id)
        assert not agent.take_step(AUCTION_BID_TOOL, table, command_id="agent-bid", value=18).is_error
        pulses.clear()

        wait(skat, time, 10 * ASK_AGAIN_AFTER)

        assert pulses == []

    def test_an_act_of_another_seat_starts_the_pause_afresh_while_the_seat_still_waits(
        self, skat, time, agent, forehand_auction, pulses
    ):
        table = a_result_stands(forehand_auction)
        agent.view(table.table_id)
        wait(skat, time, ASK_AGAIN_AFTER - 10)
        person_posts(table, TABLE_READY_SUFFIX, MIDDLEHAND, ordinal=1)
        moved = agent.view(table.table_id)
        pulses.clear()

        wait(skat, time, 10)
        before_the_new_deadline = agent.view(table.table_id)
        wait(skat, time, ASK_AGAIN_AFTER - 10)
        asked = agent.view(table.table_id)

        version = table.record.version
        assert (moved["awaits_you"], before_the_new_deadline["revision"]) == (True, revision_of(version, 0))
        assert (asked["revision"], pulses) == (
            revision_of(version, 1),
            [(account_of(skat, agent), view_uri_of(table.table_id))],
        )


class TestTwoAgentsAtOneTable:
    """The awaited agent opened the table and holds the middlehand chair; the other agent sits at the rearhand's."""

    @pytest.fixture
    def awaited(self, skat, issuer):
        return Agent(skat, issuer, "awaited-agent", agent_name="Mozart")

    @pytest.fixture
    def other(self, skat, issuer):
        return Agent(skat, issuer, OTHER_AGENT_SUBJECT, agent_name="Bach")

    @pytest.fixture
    def table_id(self, skat, awaited, other):
        table_id = awaited.open_table().json()["id"]
        skat.sit(skat.member()[0], table_id, 2)
        other.sit_down(table_id, 3)
        with_known_deal(skat, table_id)
        return table_id

    def test_the_agent_that_the_table_does_not_wait_for_gets_no_new_revision_and_no_pulse(
        self, skat, time, awaited, other, table_id, pulses
    ):
        views = {each: each.view(table_id) for each in (awaited, other)}
        pulses.clear()

        wait(skat, time, ASK_AGAIN_AFTER)

        assert (views[awaited]["awaits_you"], views[other]["awaits_you"]) == (True, False)
        assert pulses == [(account_of(skat, awaited), view_uri_of(table_id))]
        assert awaited.view(table_id)["revision"] == views[awaited]["revision"] + 1
        assert other.view(table_id)["revision"] == views[other]["revision"]

    def test_an_agent_that_reads_after_a_deadline_has_passed_reads_that_ask_and_is_pulsed_for_the_rest(
        self, skat, time, awaited, other, table_id, pulses
    ):
        version = other.view(table_id)["state"]["version"]
        wait(skat, time, ASK_AGAIN_AFTER + 10)
        pulses.clear()

        late = awaited.view(table_id)
        wait(skat, time, ASK_AGAIN_AFTER)

        assert late["revision"] == revision_of(version, 1)
        assert pulses == [(account_of(skat, awaited), view_uri_of(table_id))] * (ASKS_AGAIN - 1)


class TestAnAskLeavesTheTableAlone:
    def test_the_tables_version_the_stored_rows_and_the_version_a_command_names_are_as_before(
        self, skat, time, agent, middlehand_auction
    ):
        table = middlehand_auction
        agent.view(table.table_id)
        before = stored(skat)

        wait(skat, time, ASK_AGAIN_AFTER)
        asked = agent.view(table.table_id)
        after_the_ask = stored(skat)
        bid = agent.call(
            AUCTION_BID_TOOL,
            table_id=table.table_id,
            command_id="agent-bid",
            version=asked["state"]["version"],
            value=18,
        )

        assert after_the_ask == before
        assert asked["state"]["version"] == before[0][table.table_id].version
        assert bid.is_error is False


class TestWhereAPulseIsScheduled:
    def test_the_pulses_are_scheduled_on_the_event_loops_thread_and_once_for_a_version_and_agent(
        self, skat, time, agent, middlehand_auction
    ):
        loop_thread = skat.client.portal.call(threading.get_ident)
        time.callers.clear()
        pending = time.pending

        agent.view(middlehand_auction.table_id)
        agent.view(middlehand_auction.table_id)

        assert time.callers == [loop_thread] * ASKS_AGAIN
        assert time.pending == pending + ASKS_AGAIN

    def test_stopping_the_presence_cancels_the_pulses_with_the_other_timers(
        self, skat, time, agent, middlehand_auction, pulses
    ):
        agent.view(middlehand_auction.table_id)
        pulses.clear()

        skat.app.state.stop_streams()
        wait(skat, time, 10 * ASK_AGAIN_AFTER)

        assert (time.pending, pulses) == (0, [])


class TestARestartAndALapsedLease:
    def test_a_restart_reads_no_ask_and_asks_again_one_pause_after_its_first_read(
        self, skat, issuer, hold, time, agent, middlehand_auction, changes, pulses
    ):
        table_id = middlehand_auction.table_id
        agent.view(table_id)
        wait(skat, time, ASK_AGAIN_AFTER)
        version = agent.view(table_id)["state"]["version"]
        restarted_time = FakeTime()

        restarted = Skat(
            lambda: hold,
            store=skat.store,
            stores=skat.stores,
            issuer_transports=issuer.transports,
            chair_clock=restarted_time.clock,
            chair_scheduler=restarted_time,
            now=restarted_time.moment,
            resource_changes=changes,
        )
        with restarted.client:
            returned = Agent(restarted, issuer, agent.subject)
            first = returned.view(table_id)
            pulses.clear()
            restarted.client.portal.call(restarted_time.advance, ASK_AGAIN_AFTER)
            asked = returned.view(table_id)

        assert (first["revision"], asked["revision"]) == (revision_of(version, 0), revision_of(version, 1))
        assert pulses == [(account_of(restarted, returned), view_uri_of(table_id))]

    def test_an_agent_that_returns_after_its_lease_lapsed_reads_the_asks_due_so_far_and_no_more_than_the_cap(
        self, skat, time, agent, middlehand_auction
    ):
        table_id = middlehand_auction.table_id
        version = agent.view(table_id)["state"]["version"]

        wait(skat, time, LEASE_SECONDS + (ASKS_AGAIN + 3) * ASK_AGAIN_AFTER)

        assert agent.view(table_id)["revision"] == revision_of(version, ASKS_AGAIN)


class TestWhenTheTableEndsThePulseTellsNobody:
    def test_the_deadline_after_the_end_delivers_nothing_on_a_stream_that_is_open(
        self, skat, time, sdk, middlehand_auction
    ):
        """The table is ended in the store with no view read after it: the stream delivers the standing change and
        nothing of the table.
        """
        table_id = middlehand_auction.table_id

        with sdk.connected() as session, session.listening() as events:
            session.view(table_id)
            skat.store.tables[table_id] = EndedTable(
                TableId(table_id), skat.store.tables[table_id].version + 1, EndReason.EMPTY, 3600
            )
            wait(skat, time, ASK_AGAIN_AFTER)
            a_standing_change(skat, time)

            assert events.next_uri() == STANDING_URI


class TestAnEndedTablesWaitIsDropped:
    class _Ending:
        """The service whose commands answer whether they ended the table."""

        def __init__(self, ended):
            self._ended = ended

        def end_empty_table(self, _table_id, _connected_accounts, _empty_seconds):
            return self._ended

        def note_presence(self, _table_id, _connected_accounts, _empty_seconds):
            return self._ended

    @pytest.mark.parametrize("closing", ["end", "note"])
    @pytest.mark.parametrize("ended", [True, False])
    def test_the_empty_table_drops_the_wait_when_its_command_ended_the_table_and_keeps_it_otherwise(
        self, closing, ended
    ):
        clock = AskClock(Moments())
        clock.see(TABLE, 6)
        empty = _empty_table(SimpleNamespace(empty_table_seconds=60), self._Ending(ended), clock)

        answer = asyncio.run(getattr(empty, closing)(TABLE, nullcontext(frozenset())))

        assert (answer, clock.is_current(TABLE, 6)) == (ended, not ended)


class _OvertakenDuringTheRead:
    """The service whose read of a view is overtaken: `overtaking` runs on the event loop after the store was read
    and before the read goes on, as the table's end or a newer read does.
    """

    def __init__(self, tables, loop, overtaking):
        self._tables = tables
        self._loop = loop
        self._overtaking = overtaking

    def member_view(self, account_id, table_id, connected_accounts):
        member = self._tables.member_view(account_id, table_id, connected_accounts)
        overtaken = threading.Event()

        def overtake():
            self._overtaking()
            overtaken.set()

        self._loop.call_soon_threadsafe(overtake)
        overtaken.wait()
        return member


class TestAViewReadWhileTheTableEnds:
    def test_leaves_no_wait_and_no_pulse_behind(self, skat, agent, middlehand_auction):
        table_id = middlehand_auction.table_id
        version = middlehand_auction.record.version
        asks = AskClock(Moments())
        scheduler = FakeTime()
        presence = SimpleNamespace(connected=lambda _table_id: frozenset())

        async def read():
            tables = _OvertakenDuringTheRead(skat.tables, asyncio.get_running_loop(), partial(asks.drop, table_id))
            standings = MemberStandings(tables, presence, asks, scheduler, RecordedChanges())
            token_carries_agent_facts.set(True)
            return await standings.read(Principal(iss="an-issuer", sub=account_of(skat, agent)), view_uri_of(table_id))

        view = asyncio.run(read())

        assert view.revision == revision_of(version, 0)
        assert (asks.is_current(table_id, version), scheduler.pending) == (False, 0)


class TestAPulseOvertakenDuringItsRead:
    @pytest.mark.parametrize("overtaking", ["the table ends", "the table moves on"])
    def test_tells_nobody(self, skat, agent, middlehand_auction, overtaking):
        table_id = middlehand_auction.table_id
        version = middlehand_auction.record.version
        scheduler = FakeTime()
        asks = AskClock(scheduler.clock)
        overtakes = {
            "the table ends": partial(asks.drop, table_id),
            "the table moves on": partial(asks.see, table_id, version + 1),
        }
        armed = []
        changes = RecordedChanges()
        presence = SimpleNamespace(connected=lambda _table_id: frozenset())

        async def read_then_wait_past_the_deadline():
            tables = _OvertakenDuringTheRead(
                skat.tables, asyncio.get_running_loop(), lambda: armed and overtakes[overtaking]()
            )
            standings = MemberStandings(tables, presence, asks, scheduler, changes)
            token_carries_agent_facts.set(True)
            await standings.read(Principal(iss="an-issuer", sub=account_of(skat, agent)), view_uri_of(table_id))
            armed.append(True)
            await scheduler.advance(ASK_AGAIN_AFTER)

        asyncio.run(read_then_wait_past_the_deadline())

        assert changes.told == []


class TestAScriptedClientIsAskedAgain:
    def test_a_client_that_makes_no_call_on_its_first_turn_is_woken_again_reads_a_new_revision_and_plays(
        self, skat, time, sdk, forehand_auction
    ):
        table = forehand_auction

        with sdk.connected() as session, session.listening() as events:
            table.middlehand_bids()
            view = events.woken_view(table.table_id)
            wait(skat, time, ASK_AGAIN_AFTER)
            asked = events.woken_view(table.table_id)
            answer = session.call(
                AUCTION_HOLD_TOOL,
                table_id=table.table_id,
                command_id="agent-hold",
                version=asked["state"]["version"],
            )
            moved = session.view(table.table_id)

        assert (view["awaits_you"], asked["awaits_you"], asked["state"]) == (True, True, view["state"])
        assert asked["revision"] == view["revision"] + 1
        assert (answer.is_error, moved["awaits_you"]) == (False, False)


async def _inviting(skat, table_id, request):
    return await run_in_threadpool(skat.tables.invite_agent, TableId(table_id), request)


def a_standing_change(skat, time):
    """A change of the agent's standing that nobody's removal explains: an invitation to a table of a member."""
    person = skat.member()
    table_id = skat.create(person[0]).json()["id"]
    request = InvitationRequest(SUBJECT, OWNER, OWNER, time.moment() + timedelta(seconds=INVITATION_SECONDS))
    skat.client.portal.call(_inviting, skat, table_id, request)
    skat.client.cookies.clear()


class TestAPulseThatFails:
    def test_is_logged_by_its_type_and_the_next_read_still_shows_the_ask(
        self, skat, time, agent, middlehand_auction, changes
    ):
        table_id = middlehand_auction.table_id
        version = agent.view(table_id)["state"]["version"]
        changes.failure = ConnectionResetError()

        with capture_logs() as logs:
            wait(skat, time, ASK_AGAIN_AFTER)

        assert [log["error"] for log in logs if log["event"] == "member_signal_failed"] == ["ConnectionResetError"]
        assert agent.view(table_id)["revision"] == revision_of(version, 1)
