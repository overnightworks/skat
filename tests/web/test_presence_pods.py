"""Two presences on one set of stream leases, as two pods on one Redis: each counts the other's streams."""

from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.web.support.presence import HOLD_SECONDS, TABLE, connect, run


class TestWhoIsConnected:
    def test_a_stream_on_one_pod_counts_on_the_other(self, holding, elsewhere):
        connect(elsewhere, TABLE, "anna", lambda: None)

        assert run(holding.connected(TABLE)) == {"anna"}

    def test_an_account_with_a_stream_on_each_pod_counts_once_until_its_last_stream_closes(self, holding, elsewhere):
        here = connect(holding, TABLE, "anna", lambda: None)
        there = connect(elsewhere, TABLE, "anna", lambda: None)

        run(holding.close(here))
        assert run(elsewhere.connected(TABLE)) == {"anna"}
        run(elsewhere.close(there))
        assert run(holding.connected(TABLE)) == frozenset()

    def test_the_lobby_reads_every_table_from_one_read_of_the_roster(self, holding, elsewhere, leases):
        connect(elsewhere, TABLE, "anna", lambda: None)
        connect(holding, "another-table", "ben", lambda: None)
        before = leases.live_read_count

        connected = run(holding.connected_at([TABLE, "another-table", "no-table"]))

        assert connected == {TABLE: {"anna"}, "another-table": {"ben"}, "no-table": frozenset()}
        assert leases.live_read_count == before + 1


class TestTheHoldOfAChair:
    def test_does_not_start_while_the_account_has_a_stream_on_the_other_pod(self, holding, elsewhere, wakes):
        connect(elsewhere, TABLE, "anna", lambda: None)
        leaving = connect(holding, TABLE, "anna", wakes.callback("anna"))
        connect(holding, TABLE, "ben", wakes.callback("ben"))
        before = dict(wakes.counts)

        run(holding.close(leaving))

        assert holding.hold_seconds_left([TABLE]) == {}
        assert wakes.counts == before

    def test_starts_when_the_last_stream_of_the_account_on_any_pod_closes(self, holding, elsewhere):
        here = connect(holding, TABLE, "anna", lambda: None)
        there = connect(elsewhere, TABLE, "anna", lambda: None)
        run(elsewhere.close(there))

        run(holding.close(here))

        assert holding.hold_seconds_left([TABLE]) == {TABLE: {"anna": HOLD_SECONDS}}

    def test_frees_no_chair_whose_account_came_back_on_the_other_pod(self, holding, elsewhere, time, releases):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        connect(elsewhere, TABLE, "anna", lambda: None)

        run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == [False]

    def test_frees_the_chair_of_an_account_that_is_nowhere(self, holding, time, releases):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))

        run(time.advance(HOLD_SECONDS))

        assert releases.outcomes == [True]


class TestAnEmptyTable:
    def test_is_ended_with_who_is_connected_on_the_other_pod_so_that_the_decision_refuses(
        self, holding, elsewhere, time, ends
    ):
        run(holding.close(connect(holding, TABLE, "anna", lambda: None)))
        connect(elsewhere, TABLE, "ben", lambda: None)

        run(time.advance(DEFAULT_EMPTY_TABLE_SECONDS))

        assert ends.calls == [(TABLE, {"ben"})]
