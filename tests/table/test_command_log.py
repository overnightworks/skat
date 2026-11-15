"""What a table command writes to the log: one line under the fleet's name, on the trace it ran in, with the
refusal's own code and never what the person said or did.
"""

import itertools

import pytest
from logline import Outcome, current_traceparent, unit_trace

from skat.table.command_log import CommandNotRun
from skat.table.ending import CLOSE_TABLE_COMMAND
from skat.table.records import Actor, CloseTable, CreateTable, Refusal, SitDown, TableId
from skat.table.rules import CREATE_TABLE_COMMAND, SIT_DOWN_COMMAND
from skat.table.service import TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.log_lines import lines_of, logged

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
EVENT = "table_command.ended"


@pytest.fixture
def service():
    numbers = itertools.count(1)
    return TableService(FakeTableStore(), new_table_id=lambda: TableId(f"{next(numbers):032x}"))


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-open")).id


class TestTableCommandLine:
    def test_an_accepted_command_writes_one_ok_line_with_the_command_and_the_table_on_the_running_trace(
        self, service, table_id, capsys
    ):
        with logged(capsys) as lines, unit_trace(None):
            trace_id = current_traceparent().split("-")[1]
            service.sit(VISITOR, SitDown("command-sit", table_id, 2), frozenset())

        (line,) = lines_of(lines, EVENT)
        assert (line["command"], line["table_id"], line["outcome"]) == (SIT_DOWN_COMMAND, table_id, Outcome.OK)
        assert (line["duration_ms"] >= 0, line["trace_id"]) == (True, trace_id)

    def test_a_refused_command_writes_one_refused_line_with_the_refusals_own_code(self, service, table_id, capsys):
        with logged(capsys) as lines:
            service.sit(VISITOR, SitDown("command-sit", table_id, 1), frozenset())

        (line,) = lines_of(lines, EVENT)
        assert (line["outcome"], line["reason"]) == (Outcome.REFUSED, Refusal.SEAT_TAKEN)

    def test_a_command_for_no_table_is_refused_and_logs_no_id_the_client_wrote(self, service, capsys):
        with logged(capsys) as lines:
            service.sit(VISITOR, SitDown("command-sit", "not-a-table-id", 1), frozenset())

        (line,) = lines_of(lines, EVENT)
        assert (line["outcome"], line["reason"], line["table_id"]) == (Outcome.REFUSED, CommandNotRun.NO_TABLE, None)

    def test_opening_a_table_writes_one_ok_line_with_the_id_of_the_table_it_made(self, service, capsys):
        with logged(capsys) as lines:
            opened = service.create(OPENER, CreateTable(command_id="command-open"))

        (line,) = lines_of(lines, EVENT)
        assert (line["command"], line["table_id"], line["outcome"]) == (CREATE_TABLE_COMMAND, opened.id, Outcome.OK)

    def test_opening_a_table_again_under_the_same_command_id_writes_the_id_of_the_table_it_made_before(
        self, service, capsys
    ):
        opened = service.create(OPENER, CreateTable(command_id="command-open"))

        with logged(capsys) as lines:
            service.create(OPENER, CreateTable(command_id="command-open"))

        (line,) = lines_of(lines, EVENT)
        assert (line["table_id"], line["outcome"]) == (opened.id, Outcome.OK)

    @pytest.mark.parametrize(
        ("closer", "outcome", "reason"),
        [(OPENER, Outcome.OK, None), (VISITOR, Outcome.REFUSED, Refusal.NOT_ALLOWED)],
        ids=["by-the-opener", "by-another"],
    )
    def test_closing_a_table_writes_one_line_with_the_refusal_of_a_closer_who_may_not(
        self, service, table_id, capsys, closer, outcome, reason
    ):
        with logged(capsys) as lines:
            service.close(closer, CloseTable("command-close", table_id))

        (line,) = lines_of(lines, EVENT)
        assert (line["command"], line["outcome"], line.get("reason")) == (CLOSE_TABLE_COMMAND, outcome, reason)
