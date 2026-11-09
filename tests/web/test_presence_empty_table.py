import pytest
from structlog.testing import capture_logs

from skat.web.presence import CHAIR_RELEASE_RETRY_SECONDS
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    NAMED_FAILURE,
    OTHER_TABLE,
    TABLE,
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
