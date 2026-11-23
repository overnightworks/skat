import asyncio

import pytest

from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    HOLD_SWEEP_EVERY_SECONDS,
    EmptyTable,
    Presence,
)
from skat.web.presence_line import PresenceTimer
from tests.support.idle_presence import idle_agent_lease, idle_end_answers, idle_wakes
from tests.support.log_lines import logged
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    OTHER_TABLE,
    TABLE,
    Notes,
    Wakes,
    chair_hold,
    connect,
    failed_timers,
    lapse_of,
    run,
    serve_lapses,
)


class TestTheEmptySweep:
    def test_asks_for_the_end_of_a_table_whose_wait_is_up_with_who_is_connected_then(self, holding, time, ends):
        ends.due_now = [TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert ends.calls == [(TABLE, frozenset())]

    def test_sweeps_every_hold_sweep_and_not_before(self, holding, time, ends):
        ends.due_now = [TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS - 1))
        assert ends.calls == []

        run(time.advance(1))
        assert ends.calls == [(TABLE, frozenset())]

    def test_asks_for_each_due_table_and_for_none_that_is_not_due(self, holding, time, ends):
        ends.due_now = [TABLE, OTHER_TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert ends.calls == [(TABLE, frozenset()), (OTHER_TABLE, frozenset())]

    def test_a_stream_opening_before_the_check_holds_the_row_is_read_as_connected(self, holding, time, ends, wakes):
        async def ben_arrives():
            await holding.subscribe(TABLE, "ben", wakes.callback("ben"))

        ends.meanwhile = ben_arrives
        ends.due_now = [TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert ends.calls == [(TABLE, frozenset({"ben"}))]
        assert wakes.counts["ben"] == 0

    @pytest.mark.parametrize(("ended", "woken"), [(True, 1), (False, 0)], ids=["ended", "refused"])
    def test_an_end_wakes_the_streams_that_arrived_meanwhile_and_a_refused_end_wakes_nobody(
        self, holding, time, ends, wakes, ended, woken
    ):
        async def ben_arrives_during_the_end():
            await holding.subscribe(TABLE, "ben", wakes.callback("ben"))

        ends.within = ben_arrives_during_the_end
        ends.ended = ended
        ends.due_now = [TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert wakes.counts["ben"] == woken

    def test_a_stream_cancelled_while_its_hold_is_cleared_leaves_the_table_to_end(self, holding, time, holds, ends):
        clearing = asyncio.Event()

        async def clear_until_cancelled():
            clearing.set()
            await asyncio.Event().wait()

        holds.on_clear = clear_until_cancelled
        ends.due_now = [TABLE]
        holding.start_sweeps()

        async def scenario():
            returning = asyncio.create_task(holding.subscribe(TABLE, "anna", lambda: None))
            await clearing.wait()
            returning.cancel()
            await asyncio.gather(returning, return_exceptions=True)
            await time.advance(HOLD_SWEEP_EVERY_SECONDS)

        run(scenario())

        assert ends.calls == [(TABLE, frozenset())]

    def test_presence_stopped_before_the_check_enters_its_context_ends_nothing(self, holding, time, ends):
        async def stops():
            holding.stop()

        ends.meanwhile = stops
        ends.due_now = [TABLE]
        holding.start_sweeps()

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert (ends.calls, ends.outcomes, time.pending) == ([(TABLE, None)], [False], 0)

    def test_stopping_ends_the_sweeps(self, holding, time, ends):
        ends.due_now = [TABLE]
        holding.start_sweeps()

        holding.stop()
        run(time.advance(HOLD_SWEEP_EVERY_SECONDS * 2))

        assert (time.pending, ends.calls) == (0, [])

    def test_a_failed_end_writes_the_streak_warning_and_the_next_sweep_asks_again(self, holding, time, ends, capsys):
        ends.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        ends.due_now = [TABLE]
        holding.start_sweeps()

        with logged(capsys) as lines:
            run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert failed_timers(lines) == [(PresenceTimer.EMPTY_TABLE_END, "warning")]
        assert "anna" not in str(lines)
        assert ends.calls == []

        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))
        assert ends.calls == [(TABLE, frozenset())]

    def test_a_failed_read_of_the_due_tables_writes_the_sweeps_streak_warning_and_the_next_sweep_reads_again(
        self, holding, time, ends, capsys
    ):
        ends.due_failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        ends.due_now = [TABLE]
        holding.start_sweeps()

        with logged(capsys) as lines:
            run(time.advance(HOLD_SWEEP_EVERY_SECONDS))

        assert (failed_timers(lines), ends.calls) == ([(PresenceTimer.EMPTY_SWEEP, "warning")], [])
        run(time.advance(HOLD_SWEEP_EVERY_SECONDS))
        assert ends.calls == [(TABLE, frozenset())]


@pytest.fixture
def notes():
    return Notes()


@pytest.fixture
def noting(time, holds, deals, ends, notes, leases):
    return Presence(
        chair_hold(time, holds),
        deals.port(),
        EmptyTable(ends.end, notes.note, ends.due),
        idle_agent_lease(),
        idle_wakes(),
        leases,
        idle_end_answers(),
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
        run(noting.close(leaving))

        run(time.advance(0))

        assert notes.calls[-1] == (TABLE, frozenset())

    def test_a_leave_while_another_stays_writes_nothing(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        connect(noting, TABLE, "ben", lambda: None)
        run(noting.close(leaving))

        run(time.advance(0))

        assert len(notes.calls) == 1

    def test_a_failed_arrival_write_fails_the_stream_and_leaves_no_stream_behind(self, noting, notes):
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]

        with pytest.raises(ConnectionError):
            connect(noting, TABLE, "anna", lambda: None)

        assert run(noting.connected(TABLE)) == frozenset()

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
        run(noting.close(leaving))
        connect(noting, TABLE, "ben", wakes.callback("ben"))
        before = wakes.counts["ben"]
        notes.ended = True

        run(time.advance(0))

        assert wakes.counts["ben"] == before + 1

    def test_a_failed_leave_write_writes_the_streak_warning_and_is_retried_while_the_presence_runs(
        self, noting, time, notes, capsys
    ):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        run(noting.close(leaving))

        with logged(capsys) as lines:
            run(time.advance(0))
        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert failed_timers(lines) == [(PresenceTimer.EMPTY_SINCE_WRITE, "warning")]
        assert notes.calls[-1] == (TABLE, frozenset())

    def test_a_retried_leave_write_notes_who_is_connected_when_it_runs_after_a_reconnect(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        notes.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        run(noting.close(leaving))
        run(time.advance(0))
        connect(noting, TABLE, "anna", lambda: None)
        calls_after_reconnect = len(notes.calls)

        run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

        assert notes.calls[calls_after_reconnect:] == [(TABLE, frozenset({"anna"}))]

    def test_a_stopped_presence_writes_no_leave(self, noting, time, notes):
        leaving = connect(noting, TABLE, "anna", lambda: None)
        noting.stop()
        run(noting.close(leaving))

        run(time.advance(0))

        assert len(notes.calls) == 1

    def test_a_lapse_is_handed_again_until_the_empty_table_is_noted(self, noting, notes, leases):
        failure = ConnectionError(FAILURE_NAMING_AN_ACCOUNT)
        notes.failures = [failure]
        leases.lapses = [lapse_of(TABLE, "anna")]

        run(serve_lapses(noting, leases))

        assert (leases.handler_failures, notes.calls) == ([failure], [(TABLE, frozenset())])
