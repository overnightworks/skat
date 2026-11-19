"""The server re-reads the stored end proposals every round while it serves; a failed read is logged by its type and the
next round reads again, and a stopped server asks for no further round.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from skat.table.service import TableService
from tests.support.log_lines import lines_of, logged
from tests.support.unplayed_tables import UnplayedTables

EVENT = "end_answers_read.failed"


class Unreadable(TableService):
    reading = False

    def pending_end_answers(self):
        if Unreadable.reading:
            raise ConnectionError("account-anna")
        return super().pending_end_answers()


@pytest.fixture
def unplayed(sign_in_settings):
    Unreadable.reading = False
    return UnplayedTables(sign_in_settings, Unreadable)


class TestTheEndAnswerRecovery:
    def test_a_failed_read_is_logged_by_its_type_and_the_next_round_is_asked_for(self, unplayed, capsys):
        with TestClient(unplayed.app()) as client:
            ((_, round_),) = unplayed.scheduler.recoveries()
            Unreadable.reading = True
            with logged(capsys) as lines:
                client.portal.call(round_)

            assert len(unplayed.scheduler.recoveries()) == 2

        (line,) = lines_of(lines, EVENT)
        assert line["error_type"] == "ConnectionError"
        assert "account-anna" not in str(lines)

    def test_a_stopped_server_asks_for_no_further_round(self, unplayed):
        async def serve_and_stop():
            app = unplayed.app()
            async with app.router.lifespan_context(app):
                ((_, round_),) = unplayed.scheduler.recoveries()
            unplayed.scheduler.actions.clear()
            await round_()

        asyncio.run(serve_and_stop())

        assert unplayed.scheduler.recoveries() == []
