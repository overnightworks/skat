import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.e2e.support.sessions import end_sessions_of
from tests.e2e.support.tables import open_new_table, plate_of, sit_in, table_id_of
from tests.support.signed_in import parsed_set_cookies

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.failure_record import FailureRecord
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e
pytest_plugins = ["pytester"]

REFUSED = 401
MISSING = 404
REPOSITORY_ROOT = Path(__file__).parents[2]
ANSWERED = 200
FORBIDDEN_HEADER_NAMES = ("cookie", "x-forwarded-for", "user-agent", "authorization", "origin")


def answer_line(status: int, method: str, path: str) -> re.Pattern[str]:
    return re.compile(rf"^\+\d+\.\d{{3}}s response {status} {method} {re.escape(path)}$", re.MULTILINE)


def watching_with_a_second_viewer(
    open_person: Callable[..., Page], server: RunningServer, member_of: Callable[[Page], SeededMember]
) -> tuple[Page, Page, str]:
    anna = open_person(username="anna")
    path = open_new_table(anna, server)
    viewer = open_person()
    viewer.goto(f"{server.base_url}{path}")
    sit_in(viewer, 2)
    expect(plate_of(anna, 2)).to_have_text(member_of(viewer).account.username)
    return anna, viewer, path


def test_the_record_names_the_person_the_table_and_the_stream_with_its_messages(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    failure_record: FailureRecord,
) -> None:
    _, _, path = watching_with_a_second_viewer(open_person, e2e_server, member_of)

    record = failure_record.render()

    assert "anna" in record
    assert answer_line(ANSWERED, "GET", path).search(record)
    events = f"{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}"
    assert answer_line(ANSWERED, "GET", events).search(record)
    assert re.search(rf"^\+\d+\.\d{{3}}s message {re.escape(events)} \d+ bytes$", record, re.MULTILINE)


def test_the_record_shows_a_refusal(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    failure_record: FailureRecord,
) -> None:
    anna, _, path = watching_with_a_second_viewer(open_person, e2e_server, member_of)
    end_sessions_of(e2e_server, "anna")

    anna.evaluate("path => fetch(path)", f"{TABLES_PATH}/{table_id_of(path)}")

    assert answer_line(REFUSED, "GET", f"{TABLES_PATH}/{table_id_of(path)}").search(failure_record.render())


def test_the_record_holds_no_cookie_header_or_name_of_the_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    failure_record: FailureRecord,
) -> None:
    anna, viewer, _ = watching_with_a_second_viewer(open_person, e2e_server, member_of)

    record = failure_record.render()

    cookie_values = [
        morsel.value
        for member in (member_of(anna), member_of(viewer))
        for header in member.set_cookie_headers
        for _, morsel in parsed_set_cookies([header])
    ]
    assert cookie_values
    assert not [value for value in cookie_values if value in record]
    assert not [name for name in FORBIDDEN_HEADER_NAMES if name in record.lower()]
    assert member_of(viewer).account.username not in record


def test_the_console_error_of_a_failed_request_names_the_path_it_asked(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    failure_record: FailureRecord,
) -> None:
    anna, _, path = watching_with_a_second_viewer(open_person, e2e_server, member_of)
    unknown = f"{TABLES_PATH}/{table_id_of(path)}-unknown"

    anna.evaluate("path => fetch(path)", unknown)

    assert answer_line(MISSING, "GET", unknown).search(failure_record.render())
    assert re.search(
        rf"^\+\d+\.\d{{3}}s log\.error: Failed to load resource: .*\(Not Found\) {re.escape(unknown)}$",
        failure_record.render(),
        re.MULTILINE,
    )


TIMELINE = "the timeline of the pages"
INNER_CONFTEST = f"""
import pytest
from tests.e2e.conftest import pytest_runtest_makereport
from tests.e2e.support.failure_record import FailureRecord


class WatchedPages(FailureRecord):
    def render(self):
        return {TIMELINE!r}


@pytest.fixture
def failure_record():
    return WatchedPages()
"""
FAILS_IN_CALL = """
def test_it(failure_record):
    assert False
"""
FAILS_IN_TEARDOWN = """
import pytest


@pytest.fixture
def page_errors(failure_record):
    errors = []
    yield errors
    assert errors == []


def test_it(page_errors):
    page_errors.append("Failed to load resource")
"""
PASSES = """
def test_it(failure_record):
    pass
"""


@pytest.mark.parametrize(
    ("test_source", "prints"),
    [(FAILS_IN_CALL, True), (FAILS_IN_TEARDOWN, True), (PASSES, False)],
    ids=["fails in the call", "fails in the teardown", "passes"],
)
def test_a_failed_test_prints_its_timeline_in_the_call_and_the_teardown(
    pytester: pytest.Pytester, test_source: str, prints: bool
) -> None:
    pytester.makeini(f"[pytest]\npythonpath = {REPOSITORY_ROOT} {REPOSITORY_ROOT / 'src'}\n")
    pytester.makeconftest(INNER_CONFTEST)
    pytester.makepyfile(test_source)

    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")

    assert (TIMELINE in result.stdout.str()) is prints
