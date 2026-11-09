import asyncio

import pytest
from structlog.testing import capture_logs

from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    NEXT_DEAL_PAUSE_SECONDS,
    ChairHold,
    EmptyTable,
    NextDeal,
    Presence,
)
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.idle_presence import idle_agent_lease
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    HOLD_SECONDS,
    NAMED_FAILURE,
    OTHER_TABLE,
    TABLE,
    Wakes,
    connect,
    run,
)

MINUTE = 60


class TestWhenTheTimerStarts:
    def test_a_created_table_ends_after_the_wait_and_not_a_moment_before(self, holding, time, ends):
        holding.watch_empty_table(TABLE)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS - 1))
        assert ends.calls == []

        run(time.advance(1))
        assert ends.calls == [(TABLE, frozenset())]

    def test_a_second_create_retry_neither_restarts_nor_stretches_the_wait(self, holding, time, ends):
        holding.watch_empty_table(TABLE)
        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS - MINUTE))

        holding.watch_empty_table(TABLE)
        run(time.advance(MINUTE))

        assert ends.calls == [(TABLE, frozenset())]

    def test_a_created_table_somebody_is_connected_to_starts_none(self, holding, time):
        connect(holding, TABLE, "anna", lambda: None)

        holding.watch_empty_table(TABLE)

        assert time.pending == 0

    def test_the_last_stream_ending_starts_the_wait_from_then(self, holding, time, ends):
        leaving = connect(holding, TABLE, "anna", lambda: None)
        run(time.advance(MINUTE))
        holding.unsubscribe(leaving)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS - 1))
        assert ends.calls == []

        run(time.advance(1))
        assert ends.calls == [(TABLE, frozenset())]

    def test_a_stream_ending_while_another_account_stays_connected_starts_no_wait_for_the_table(
        self, holding, time, ends
    ):
        leaving = connect(holding, TABLE, "anna", lambda: None)
        connect(holding, TABLE, "ben", lambda: None)

        holding.unsubscribe(leaving)
        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == []

    def test_a_watcher_who_stays_keeps_the_table_for_good(self, holding, time, ends):
        holding.watch_empty_table(TABLE)
        connect(holding, TABLE, "ben", lambda: None)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS * 4))

        assert ends.calls == []

    def test_each_table_has_its_own_wait(self, holding, time, ends):
        holding.watch_empty_table(TABLE)
        holding.watch_empty_table(OTHER_TABLE)
        connect(holding, OTHER_TABLE, "ben", lambda: None)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == [(TABLE, frozenset())]

    def test_a_return_and_a_second_leave_restart_the_wait_and_the_first_timer_ends_nothing(self, holding, time, ends):
        first_leave = connect(holding, TABLE, "anna", lambda: None)
        holding.unsubscribe(first_leave)
        run(time.advance(20 * MINUTE))
        second_leave = connect(holding, TABLE, "anna", lambda: None)
        run(time.advance(5 * MINUTE))
        holding.unsubscribe(second_leave)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS - 25 * MINUTE))
        assert ends.calls == []

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS - 5 * MINUTE))
        assert ends.calls == [(TABLE, frozenset())]


class TestWhenTheCheckRuns:
    def test_a_stream_opening_before_the_check_holds_the_row_leaves_the_table_alone(self, holding, time, ends, wakes):
        async def ben_arrives():
            await holding.subscribe(TABLE, "ben", wakes.callback("ben"))

        ends.meanwhile = ben_arrives
        holding.watch_empty_table(TABLE)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == [(TABLE, None)]
        assert wakes.counts["ben"] == 0

    @pytest.mark.parametrize(("ended", "woken"), [(True, 1), (False, 0)], ids=["ended", "refused"])
    def test_an_end_wakes_the_streams_that_arrived_meanwhile_and_a_refused_end_wakes_nobody(
        self, holding, time, ends, wakes, ended, woken
    ):
        async def ben_arrives_during_the_end():
            await holding.subscribe(TABLE, "ben", wakes.callback("ben"))

        ends.within = ben_arrives_during_the_end
        ends.ended = ended
        holding.watch_empty_table(TABLE)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert wakes.counts["ben"] == woken

    def test_a_stream_cancelled_while_it_waits_for_a_freeing_leaves_the_table_to_end(
        self, holding, time, releases, ends
    ):
        writing = asyncio.Event()
        commit = asyncio.Event()

        async def write_until_released():
            writing.set()
            await commit.wait()

        async def scenario():
            expiry = asyncio.create_task(time.advance(HOLD_SECONDS))
            await writing.wait()
            returning = asyncio.create_task(holding.subscribe(TABLE, "anna", lambda: None))
            await asyncio.sleep(0)
            returning.cancel()
            commit.set()
            await expiry
            await time.advance(DEFAULT_EMPTY_TABLE_SECONDS)

        holding.unsubscribe(connect(holding, TABLE, "anna", lambda: None))
        releases.within = write_until_released

        run(scenario())

        assert ends.calls == [(TABLE, frozenset())]

    def test_presence_stopped_before_the_check_enters_its_context_ends_nothing(self, holding, time, ends):
        async def stops():
            holding.stop()

        ends.meanwhile = stops
        holding.watch_empty_table(TABLE)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert (ends.calls, ends.outcomes, time.pending) == ([(TABLE, None)], [False], 0)

    def test_a_stopped_presence_starts_no_wait(self, holding, time):
        holding.stop()

        holding.watch_empty_table(TABLE)
        holding.unsubscribe(connect(holding, OTHER_TABLE, "anna", lambda: None))

        assert time.pending == 0


class TestWhenTheStoreFails:
    def test_a_failed_end_is_logged_by_name_and_retried_after_the_retry_delay(self, holding, time, ends):
        ends.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        holding.watch_empty_table(TABLE)

        with capture_logs() as logs:
            run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
        assert (logs[0]["table_id"], "anna" in str(logs)) == (TABLE, False)
        assert ends.calls == []

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))
        assert ends.calls == [(TABLE, frozenset())]

    def test_a_stream_opening_while_the_retry_waits_keeps_the_table(self, holding, time, ends):
        ends.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        holding.watch_empty_table(TABLE)
        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        connect(holding, TABLE, "anna", lambda: None)
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert ends.calls == []


class TestWhenTheServerStops:
    def test_stopping_cancels_every_pending_wait(self, holding, time, ends):
        holding.watch_empty_table(TABLE)

        holding.stop()
        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS * 2))

        assert (time.pending, ends.calls) == (0, [])


class Notes:
    """The note command as the presence calls it: who was connected when each write held the row."""

    def __init__(self):
        self.calls = []
        self.failures = []
        self.ended = False
        self.meanwhile = None

    async def note(self, table_id, connected_accounts):
        if self.meanwhile is not None:
            await self.meanwhile()
        if self.failures:
            raise self.failures.pop(0)
        with connected_accounts as connected:
            self.calls.append((table_id, connected))
        return self.ended


@pytest.fixture
def notes():
    return Notes()


@pytest.fixture
def noting(time, releases, deals, ends, notes):
    return Presence(
        ChairHold(HOLD_SECONDS, time.clock, time, releases.free_chair),
        NextDeal(NEXT_DEAL_PAUSE_SECONDS, deals.deal_next),
        EmptyTable(DEFAULT_EMPTY_TABLE_SECONDS, ends.end, notes.note),
        idle_agent_lease(),
    )


class TestTheStoredTimeSinceNobodyWasThere:
    def test_the_first_arrival_writes_before_the_stream_has_its_subscription_returned(self, noting, notes):
        connect(noting, TABLE, "anna", lambda: None)

        assert notes.calls == [(TABLE, frozenset({"anna"}))]

    def test_a_second_stream_on_a_table_someone_is_at_writes_nothing(self, noting, notes):
        connect(noting, TABLE, "anna", lambda: None)
        connect(noting, TABLE, "ben", lambda: None)

        assert len(notes.calls) == 1

    def test_the_last_leave_writes_with_nobody_connected(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        noting.unsubscribe(leaving)

        run(time.advance(0))

        assert notes.calls[-1] == (TABLE, frozenset())

    def test_a_leave_while_another_stays_writes_nothing(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        connect(noting, TABLE, "ben", lambda: None)
        noting.unsubscribe(leaving)

        run(time.advance(0))

        assert len(notes.calls) == 1

    def test_a_failed_arrival_write_fails_the_stream_and_leaves_no_stream_behind(self, noting, notes):
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]

        with pytest.raises(ConnectionError):
            connect(noting, TABLE, "anna", lambda: None)

        assert noting.connected(TABLE) == frozenset()

    def test_a_reconnect_after_a_failed_arrival_writes_again(self, noting, notes):
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        with pytest.raises(ConnectionError):
            connect(noting, TABLE, "anna", lambda: None)

        connect(noting, TABLE, "anna", lambda: None)

        assert notes.calls == [(TABLE, frozenset({"anna"}))]

    def test_a_failed_first_arrival_writes_again_for_a_stream_that_registered_while_it_ran(self, noting, time, notes):
        async def scenario():
            writing, go_on = asyncio.Event(), asyncio.Event()

            async def hold_the_write():
                writing.set()
                await go_on.wait()

            notes.meanwhile = hold_the_write
            notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
            first = asyncio.create_task(noting.subscribe(TABLE, "anna", lambda: None))
            await writing.wait()
            notes.meanwhile = None
            await noting.subscribe(TABLE, "ben", lambda: None)
            go_on.set()
            with pytest.raises(ConnectionError):
                await first
            await time.advance(0)

        run(scenario())

        assert notes.calls == [(TABLE, frozenset({"ben"}))]

    def test_an_arrival_that_ends_the_table_wakes_its_streams(self, noting, notes):
        wakes = Wakes()
        notes.ended = True

        connect(noting, TABLE, "anna", wakes.callback("anna"))

        assert wakes.counts["anna"] == 1

    def test_a_leave_write_that_ends_the_table_wakes_the_streams_open_by_then(self, noting, time, notes):
        wakes = Wakes()
        leaving = connect(noting, TABLE, "anna", wakes.callback("anna"))
        noting.unsubscribe(leaving)
        connect(noting, TABLE, "ben", wakes.callback("ben"))
        before = wakes.counts["ben"]
        notes.ended = True

        run(time.advance(0))

        assert wakes.counts["ben"] == before + 1

    def test_a_failed_leave_write_is_logged_by_name_and_retried_while_the_presence_runs(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        noting.unsubscribe(leaving)

        with capture_logs() as logs:
            run(time.advance(0))
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert [(log["error"], log["table_id"]) for log in logs] == [("ConnectionError", TABLE)]
        assert notes.calls[-1] == (TABLE, frozenset())

    def test_a_retried_leave_write_notes_who_is_connected_when_it_runs_after_a_reconnect(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        noting.unsubscribe(leaving)
        run(time.advance(0))
        connect(noting, TABLE, "anna", lambda: None)
        calls_after_reconnect = len(notes.calls)

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert notes.calls[calls_after_reconnect:] == [(TABLE, frozenset({"anna"}))]

    def test_a_stopped_presence_writes_no_leave(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        noting.stop()
        noting.unsubscribe(leaving)

        run(time.advance(0))

        assert len(notes.calls) == 1


class TestTheWaitAfterAStart:
    def test_each_table_found_at_the_start_ends_when_its_own_left_wait_passes(self, holding, time, ends):
        holding.watch_empty_tables({TABLE: 20 * MINUTE, OTHER_TABLE: 5 * MINUTE})

        run(time.advance(5 * MINUTE))
        assert ends.calls == [(OTHER_TABLE, frozenset())]

        run(time.advance(15 * MINUTE))
        assert ends.calls == [(OTHER_TABLE, frozenset()), (TABLE, frozenset())]

    def test_a_table_found_at_the_start_ends_when_what_is_left_of_its_wait_passes(self, holding, time, ends):
        holding.watch_empty_table(TABLE, 20 * MINUTE)

        run(time.advance(20 * MINUTE - 1))
        assert ends.calls == []

        run(time.advance(1))
        assert ends.calls == [(TABLE, frozenset())]
