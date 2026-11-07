import json
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.constants import ACCOUNT_CONSOLE_PATH, ACCOUNT_PATH, AUTH_START_PATH, LOGIN_PATH
from tests.e2e.support.browser import (
    ACCOUNT_AVATAR,
    ACCOUNT_MENU,
    ISSUER_END_SESSION_URL,
    LEGAL_LINKS,
    record_page_errors,
)
from tests.e2e.support.people import DESKTOP, FORM_FACTORS
from tests.support.sign_in_settings import TEST_ISSUER

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

START_PAGE_LINE = "Tische kommen als Nächstes."
ACCOUNT_ROUTE = f"**{ACCOUNT_PATH}"
UNAUTHORIZED = 401


def open_start_page(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], **options: Any
) -> Page:
    person = record_page_errors(open_person(**options), page_errors)
    person.goto(f"{e2e_server.base_url}/")
    expect(person.get_by_text(START_PAGE_LINE)).to_be_visible()
    return person


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_start_page_shows_the_wordmark_the_account_button_the_legal_links_and_the_tables_line(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)

    expect(person).to_have_title("Skat")
    expect(person.locator(".wordmark")).to_have_text("Skat")
    expect(person.locator(ACCOUNT_AVATAR)).to_be_visible()
    legal_row = person.locator(".start-legal").get_by_role("link")
    assert {(link.inner_text(), link.get_attribute("href")) for link in legal_row.all()} == set(LEGAL_LINKS.items())
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_account_button_opens_a_menu_with_the_username_one_log_out_and_the_legal_row(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, username="felix.hummert", **form_factor)

    person.locator(ACCOUNT_AVATAR).click()

    menu = person.locator(ACCOUNT_MENU)
    expect(menu.get_by_role("link").first).to_have_text("felix.hummert")
    expect(menu.get_by_role("button", name="Log out")).to_have_count(1)
    assert {(link.inner_text(), link.get_attribute("href")) for link in menu.locator("nav a").all()} == set(
        LEGAL_LINKS.items()
    )


def test_the_menu_closes_on_escape_and_on_a_press_outside(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **DESKTOP)

    person.locator(ACCOUNT_AVATAR).click()
    expect(person.locator(ACCOUNT_MENU)).to_be_visible()
    person.keyboard.press("Escape")
    expect(person.locator(ACCOUNT_MENU)).to_be_hidden()

    person.locator(ACCOUNT_AVATAR).click()
    person.mouse.click(10, 400)
    expect(person.locator(ACCOUNT_MENU)).to_be_hidden()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_name_opens_the_account_console_in_a_new_tab_and_closes_the_menu(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(TEST_ISSUER)
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)
    console_answers: list[tuple[int, str | None]] = []
    person.context.on(
        "response",
        lambda response: (
            console_answers.append((response.status, response.header_value("location")))
            if urlsplit(response.url).path == ACCOUNT_CONSOLE_PATH
            else None
        ),
    )
    person.locator(ACCOUNT_AVATAR).click()
    name_row = person.locator(ACCOUNT_MENU).get_by_role("link").first
    expect(name_row).to_have_attribute("target", "_blank")

    with person.context.expect_event("page"):
        name_row.click()

    expect(person.locator(ACCOUNT_MENU)).to_be_hidden()
    assert console_answers[0] == (303, f"{TEST_ISSUER}/account")


def test_a_menu_the_account_cannot_name_is_called_account_and_still_logs_out(
    open_person: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = open_person(**DESKTOP)
    person.route(ACCOUNT_ROUTE, lambda route: route.fulfill(status=500, body="{}"))

    person.goto(f"{e2e_server.base_url}/")
    person.locator(ACCOUNT_AVATAR).click()

    expect(person.locator(ACCOUNT_MENU).get_by_role("link").first).to_have_text("Account")
    expect(person.locator(ACCOUNT_MENU).get_by_role("button", name="Log out")).to_be_visible()


def test_a_session_that_ended_goes_through_the_sign_in_once_when_the_account_answers_401(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    member_of: Callable[[Page], Any],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    expected_request_failures.append(TEST_ISSUER)
    person = open_person(**DESKTOP)
    sign_in_starts: list[str] = []
    person.on("request", lambda request: sign_in_starts.append(request.url) if AUTH_START_PATH in request.url else None)

    def end_the_session_and_answer_401(route: Route) -> None:
        e2e_server.stores.sessions.delete(member_of(person).session.id)
        route.fulfill(status=UNAUTHORIZED, body=json.dumps({}))

    person.route(ACCOUNT_ROUTE, end_the_session_and_answer_401)

    with person.expect_event("requestfailed"):
        person.goto(f"{e2e_server.base_url}/")

    assert len(sign_in_starts) == 1


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_signing_out_ends_the_session_and_the_sign_in_page_follows(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], Any],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)
    session_id = member_of(person).session.id
    end_session_posts: list[dict[str, list[str]]] = []

    def end_the_session_at_the_issuer(route: Route) -> None:
        form = parse_qs(route.request.post_data or "")
        end_session_posts.append(form)
        route.fulfill(status=303, headers={"location": form["post_logout_redirect_uri"][0]})

    person.route(ISSUER_END_SESSION_URL, end_the_session_at_the_issuer)
    person.locator(ACCOUNT_AVATAR).click()

    person.locator(ACCOUNT_MENU).get_by_role("button", name="Log out").click()

    expect(person.get_by_role("link", name="Log in", exact=True)).to_be_visible()
    assert urlsplit(person.url).path == LOGIN_PATH
    assert len(end_session_posts) == 1
    assert e2e_server.stores.sessions.load(session_id) is None
    assert [cookie for cookie in person.context.cookies() if cookie["name"].startswith("__Host-")] == []
