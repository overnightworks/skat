import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.constants import ACCOUNT_CONSOLE_PATH, ACCOUNT_PATH, LOGIN_PATH
from skat.web.lobby import LOBBY_EVENTS_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import (
    ACCOUNT_AVATAR,
    ACCOUNT_MENU,
    ISSUER_END_SESSION_URL,
    LEGAL_LINKS,
    NEW_TABLE_BUTTON,
    record_page_errors,
)
from tests.e2e.support.kit_words import kit_text
from tests.e2e.support.people import DESKTOP, FORM_FACTORS
from tests.support.sign_in_settings import TEST_ISSUER

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e


ACCOUNT_ROUTE = f"**{ACCOUNT_PATH}"
UNAUTHORIZED = 401


def open_start_page(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], **options: Any
) -> Page:
    person = record_page_errors(open_person(**options), page_errors)
    person.goto(f"{e2e_server.base_url}/")
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    return person


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_start_page_shows_the_wordmark_the_account_button_the_legal_links_and_the_new_table_button(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)

    expect(person).to_have_title(text(SOURCE_LANGUAGE, "app.name"))
    expect(person.locator(".wordmark")).to_have_text(text(SOURCE_LANGUAGE, "app.name"))
    expect(person.locator(ACCOUNT_AVATAR)).to_be_visible()
    legal_row = person.locator(".start-legal").get_by_role("link")
    assert {(link.inner_text(), link.get_attribute("href")) for link in legal_row.all()} == {
        (text(SOURCE_LANGUAGE, key), href) for key, href in LEGAL_LINKS.items()
    }
    expect(person.locator("body")).to_have_css("margin", "0px")
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_account_button_opens_a_menu_with_the_username_one_log_out_and_the_legal_row(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, username="felix.hummert", **form_factor)

    person.locator(ACCOUNT_AVATAR).click()

    menu = person.locator(ACCOUNT_MENU)
    expect(menu.get_by_role("link").first).to_have_text("felix.hummert")
    expect(menu.get_by_role("button", name=kit_text("account.logOut"))).to_have_count(1)
    assert {(link.inner_text(), link.get_attribute("href")) for link in menu.locator("nav a").all()} == {
        (text(SOURCE_LANGUAGE, key), href) for key, href in LEGAL_LINKS.items()
    }


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


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_account_button_and_menu_speak_german(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)

    expect(person.locator(ACCOUNT_AVATAR)).to_have_attribute("aria-label", text(SOURCE_LANGUAGE, "account.title"))
    person.locator(ACCOUNT_AVATAR).click()

    menu = person.locator(ACCOUNT_MENU)
    expect(menu.get_by_role("button", name=kit_text("account.logOut"))).to_be_visible()
    expect(person.locator("[lang=de]").locator(ACCOUNT_MENU)).to_have_count(1)


def test_a_menu_the_account_cannot_name_is_called_account_and_still_logs_out(
    open_person: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = open_person(**DESKTOP)
    person.route(ACCOUNT_ROUTE, lambda route: route.fulfill(status=500, body="{}"))

    person.goto(f"{e2e_server.base_url}/")
    person.locator(ACCOUNT_AVATAR).click()

    expect(person.locator(ACCOUNT_MENU).get_by_role("link").first).to_have_text(text(SOURCE_LANGUAGE, "account.title"))
    expect(person.locator(ACCOUNT_MENU).get_by_role("button", name=kit_text("account.logOut"))).to_be_visible()


def test_a_session_that_ended_sends_the_page_to_the_sign_in_page_once_when_the_account_answers_401(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], Any],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    # The answered 401 is the console error the browser logs for it, so only script errors are recorded.
    person = record_page_errors(open_person(**DESKTOP), page_errors, console=False)
    account_requests: list[str] = []

    def end_the_session_and_answer_401(route: Route) -> None:
        account_requests.append(route.request.url)
        e2e_server.stores.sessions.delete(member_of(person).session.id)
        route.fulfill(status=UNAUTHORIZED, body=json.dumps({}))

    person.route(ACCOUNT_ROUTE, end_the_session_and_answer_401)
    # The list's own stream would meet the ended session too and reload the page a second time; it stays unanswered.
    person.route(f"**{LOBBY_EVENTS_PATH}", lambda _route: None)

    person.goto(f"{e2e_server.base_url}/")

    expect(person).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    expect(person.get_by_role("link", name=kit_text("signIn.logIn"), exact=True)).to_be_visible()
    assert len(account_requests) == 1


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

    person.locator(ACCOUNT_MENU).get_by_role("button", name=kit_text("account.logOut")).click()

    expect(person.get_by_role("link", name=kit_text("signIn.logIn"), exact=True)).to_be_visible()
    assert urlsplit(person.url).path == LOGIN_PATH
    assert len(end_session_posts) == 1
    assert e2e_server.stores.sessions.load(session_id) is None
    assert [cookie for cookie in person.context.cookies() if cookie["name"].startswith("__Host-")] == []
