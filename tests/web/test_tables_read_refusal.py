"""A read of a table no table has the id of writes Skat's own refusal line beside the request's."""

from logline import REQUEST_EVENT, Outcome

from skat.web.tables import TABLES_PATH, TableReadRefusal
from tests.support.log_lines import lines_of, logged
from tests.web.support.skat import UNKNOWN_ID


def test_a_read_of_an_unknown_table_writes_one_refusal_line_with_its_reason_and_no_id(skat, capsys):
    headers, _ = skat.member()

    with logged(capsys) as lines:
        skat.client.get(f"{TABLES_PATH}/{UNKNOWN_ID}", headers=headers)

    (refusal,) = lines_of(lines, "table_read.refused")
    (request,) = lines_of(lines, REQUEST_EVENT)
    assert (refusal["reason"], UNKNOWN_ID in str(refusal)) == (TableReadRefusal.NO_TABLE, False)
    assert (request["status"], request["outcome"]) == (404, Outcome.OK)
