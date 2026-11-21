"""The hourly table sweep writes one line for a run that did work, one for the first of a failing run's failures and one
for its recovery, and none for a run that found nothing to do.
"""

from fastapi.testclient import TestClient
from logline import Outcome

from skat.table.service import TableService
from tests.support.log_lines import lines_of, logged
from tests.support.unplayed_tables import UNPLAYED_DAYS, UnplayedTables

EVENT = "table_sweep.ended"


class TestTheTableSweepLine:
    def test_a_run_that_ends_a_table_writes_one_line_with_its_count(self, unplayed, capsys):
        unplayed.dealt("command-open")
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(UNPLAYED_DAYS)
            with logged(capsys) as lines:
                client.portal.call(tick)

        (line,) = lines_of(lines, EVENT)
        assert (line["outcome"], line["ended_table_count"], line["failed_run_count"]) == (Outcome.OK, 1, 0)

    def test_a_run_that_finds_nothing_to_do_writes_no_line(self, unplayed, capsys):
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            with logged(capsys) as lines:
                client.portal.call(tick)

        assert lines_of(lines, EVENT) == []

    def test_a_run_that_keeps_failing_writes_its_first_failure_and_its_recovery_with_the_runs_that_failed(
        self, sign_in_settings, capsys
    ):
        class Unreadable(TableService):
            reading = True

            def unplayed_tables(self, days):
                if Unreadable.reading:
                    raise ConnectionError("account-anna")
                return super().unplayed_tables(days)

        unplayed = UnplayedTables(sign_in_settings, Unreadable)
        unplayed.dealt("command-open")
        Unreadable.reading = False
        with TestClient(unplayed.app()) as client:
            Unreadable.reading = True
            unplayed.play_on(UNPLAYED_DAYS)
            with logged(capsys) as lines:
                for _ in range(3):
                    ((_, tick),) = unplayed.scheduler.sweeps()[-1:]
                    client.portal.call(tick)
                Unreadable.reading = False
                ((_, tick),) = unplayed.scheduler.sweeps()[-1:]
                client.portal.call(tick)

        first, recovery = lines_of(lines, EVENT)
        assert (first["outcome"], first["level"], first["failed_run_count"]) == (Outcome.FAILED, "warning", 1)
        assert (recovery["outcome"], recovery["level"], recovery["failed_run_count"]) == (Outcome.OK, "info", 3)
        assert recovery["ended_table_count"] == 1
        assert "account-anna" not in str(lines_of(lines, EVENT))
