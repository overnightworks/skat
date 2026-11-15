"""What a table command writes to the log: one line under the fleet's name, on the trace of its request, with the
refusal's code and never what the person said or did.
"""

from logline import REQUEST_EVENT, Outcome

from skat.table.records import Refusal
from skat.table.rules import SIT_DOWN_COMMAND
from skat.table.service import CommandNotRun
from tests.support.log_lines import lines_of, logged


class TestTableCommand:
    def test_an_accepted_sit_writes_one_ok_line_on_the_trace_of_its_request(self, skat, capsys):
        opener, _ = skat.member()
        table_id = skat.create(opener, command_id="command-open").json()["id"]
        skat.client.cookies.clear()
        guest, _ = skat.member()

        with logged(capsys) as lines:
            skat.sit(guest, table_id, 2)

        (command,) = lines_of(lines, "table_command.ended")
        (request,) = lines_of(lines, REQUEST_EVENT)
        assert (command["command"], command["table_id"], command["outcome"]) == (SIT_DOWN_COMMAND, table_id, Outcome.OK)
        assert command["duration_ms"] >= 0
        assert command["trace_id"] == request["trace_id"] is not None

    def test_a_refused_sit_writes_one_refused_line_with_the_refusals_code(self, skat, capsys):
        opener, _ = skat.member()
        table_id = skat.create(opener, command_id="command-open").json()["id"]
        skat.client.cookies.clear()
        other, _ = skat.member()

        with logged(capsys) as lines:
            skat.sit(other, table_id, 1, command_id="command-other")

        (command,) = lines_of(lines, "table_command.ended")
        assert (command["outcome"], command["reason"]) == (Outcome.REFUSED, Refusal.SEAT_TAKEN)

    def test_a_command_for_no_table_is_refused_and_names_no_id_the_client_wrote(self, skat, capsys):
        headers, _ = skat.member()
        skat.client.cookies.clear()

        with logged(capsys) as lines:
            skat.sit(headers, "not-a-table-id", 1)

        (command,) = lines_of(lines, "table_command.ended")
        assert (command["outcome"], command["reason"], command["table_id"]) == (
            Outcome.REFUSED,
            CommandNotRun.NO_TABLE,
            None,
        )
