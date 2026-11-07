import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect
from sqlalchemy import text

from skat.web.constants import LOGIN_PATH
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors, sign_in_at_issuer
from tests.e2e.support.people import DESKTOP, FORM_FACTORS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

TABLE_URL = re.compile(rf"{re.escape(TABLE_PAGE_PREFIX)}[0-9a-f]{{32}}$")
TABLES_ROUTE = f"**{TABLES_PATH}"
UNKNOWN_ID = "0" * 32
SERVER_ERROR = 500
UNAUTHORIZED = 401


def table_count(server: RunningServer) -> int:
    with server.engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM tables")).scalar_one())


def same_origin(server: RunningServer) -> dict[str, str]:
    """The headers of a fetch from Skat's own page, which the origin check admits."""
    return {"origin": server.base_url, "accept": "application/json"}


def open_new_table(person: Page, server: RunningServer) -> str:
    person.goto(f"{server.base_url}/")
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    expect(person).to_have_url(TABLE_URL)
    return urlsplit(person.url).path


def expect_a_table_seating(person: Page, opener: str, *, mine: bool) -> None:
    expect(person.get_by_text("Warte auf Mitspieler")).to_be_visible()
    expect(person.get_by_role("button", name="Link kopieren")).to_be_visible()
    chairs = person.locator(".chair")
    expect(chairs).to_have_count(3)
    expect(person.locator(".chair[data-seat='1'] .plate")).to_have_text(opener)
    expect(person.locator(".chair.mine")).to_have_count(1 if mine else 0)
    expect(person.locator(".chair .plate", has_text="Frei")).to_have_count(2)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_member_opens_a_table_and_sits_in_chair_one_with_two_free_chairs(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    before = table_count(e2e_server)

    open_new_table(person, e2e_server)

    expect_a_table_seating(person, "anna", mine=True)
    assert table_count(e2e_server) == before + 1
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert person.evaluate("document.querySelector('.chair.mine').getBoundingClientRect().top") > person.evaluate(
        "document.querySelector('.chair:not(.mine)').getBoundingClientRect().top"
    )


def test_a_reload_shows_the_same_table_with_the_opener_still_in_chair_one(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(person, e2e_server)

    person.reload()

    expect(person).to_have_url(f"{e2e_server.base_url}{path}")
    expect_a_table_seating(person, "anna", mine=True)


def test_another_member_opening_the_link_sees_the_opener_in_chair_one_and_no_chair_of_their_own(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    visitor = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)

    visitor.goto(f"{e2e_server.base_url}{path}")

    expect_a_table_seating(visitor, "anna", mine=False)


def test_a_member_may_open_any_number_of_tables_each_under_a_link_of_its_own(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    before = table_count(e2e_server)

    first = open_new_table(person, e2e_server)
    second = open_new_table(person, e2e_server)

    assert first != second
    assert table_count(e2e_server) == before + 2


@pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-a-table", "%27%3B--"])
def test_an_unknown_or_malformed_id_shows_not_found_and_offers_a_new_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], table_id: str
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{table_id}")

    expect(person.get_by_role("heading", name="Tisch nicht gefunden")).to_be_visible()
    expect(person.get_by_text(re.compile("error|sql|postgres", re.IGNORECASE))).to_have_count(0)
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    expect(person).to_have_url(TABLE_URL)


def test_the_link_control_copies_the_absolute_link_of_the_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    person.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=e2e_server.base_url)
    path = open_new_table(person, e2e_server)

    person.get_by_role("button", name="Link kopieren").click()

    expect(person.get_by_role("status")).to_have_text("Link kopiert")
    assert person.evaluate("navigator.clipboard.readText()") == f"{e2e_server.base_url}{path}"


def test_a_refused_copy_says_so(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    open_new_table(person, e2e_server)
    person.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('refused')); }")

    person.get_by_role("button", name="Link kopieren").click()

    expect(person.get_by_role("status")).to_have_text("Der Link ließ sich nicht kopieren")


def test_a_table_the_server_cannot_read_says_so(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    path = open_new_table(person, e2e_server)
    person.route(f"**{TABLES_PATH}/*", lambda route: route.fulfill(status=SERVER_ERROR, body="{}"))

    person.goto(f"{e2e_server.base_url}{path}")

    expect(person.get_by_role("alert")).to_contain_text("Der Tisch lässt sich gerade nicht laden")


@pytest.mark.parametrize("failure", ["server error", "lost connection"])
def test_a_table_that_could_not_be_opened_says_so_and_a_retry_opens_it(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
    failure: str,
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}")
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    attempts: list[str] = []

    def fail_the_first_attempt(route: Route) -> None:
        attempts.append(route.request.post_data or "")
        if len(attempts) > 1:
            route.continue_()
        elif failure == "server error":
            route.fulfill(status=SERVER_ERROR, body="{}")
        else:
            # The server opens the table; only its answer is lost.
            route.fetch()
            route.abort()

    person.route(TABLES_ROUTE, fail_the_first_attempt)
    before = table_count(e2e_server)
    person.goto(f"{e2e_server.base_url}/")

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    expect(person.get_by_role("alert")).to_have_text("Der Tisch konnte nicht eröffnet werden.")
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    expect(person).to_have_url(TABLE_URL)
    assert attempts[0] == attempts[1]
    assert table_count(e2e_server) == before + 1


def test_a_session_that_ended_sends_the_start_page_to_the_sign_in_page_when_a_table_is_opened(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], Any],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    person = record_page_errors(open_person(**DESKTOP), page_errors, console=False)
    person.goto(f"{e2e_server.base_url}/")
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    e2e_server.stores.sessions.delete(member_of(person).session.id)
    before = table_count(e2e_server)

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    expect(person).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    assert table_count(e2e_server) == before


def test_a_visitor_without_a_session_gets_the_sign_in_page_for_a_link_and_no_table_data(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    visitor = record_page_errors(open_person(signed_in=False), page_errors)
    before = table_count(e2e_server)

    visitor.goto(f"{e2e_server.base_url}{path}")

    expect(visitor).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    expect(visitor.get_by_text("Warte auf Mitspieler")).to_have_count(0)
    answer = visitor.request.post(
        f"{e2e_server.base_url}{TABLES_PATH}", data={"command_id": "command-0001"}, headers=same_origin(e2e_server)
    )
    assert answer.status == UNAUTHORIZED
    assert table_count(e2e_server) == before


def test_a_signed_in_person_the_group_does_not_admit_gets_no_table_and_writes_none(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    outsider = record_page_errors(open_person(signed_in=False, **DESKTOP), page_errors)
    sign_in_at_issuer(outsider, e2e_server, username="ben", groups=["/apps/other"])
    outsider.goto(f"{e2e_server.base_url}{LOGIN_PATH}")
    outsider.get_by_role("link", name="Log in", exact=True).click()
    before = table_count(e2e_server)

    outsider.goto(f"{e2e_server.base_url}{path}")

    expect(outsider.get_by_text("Warte auf Mitspieler")).to_have_count(0)
    answer = outsider.request.post(
        f"{e2e_server.base_url}{TABLES_PATH}", data={"command_id": "command-0001"}, headers=same_origin(e2e_server)
    )
    assert answer.status == UNAUTHORIZED
    assert table_count(e2e_server) == before
