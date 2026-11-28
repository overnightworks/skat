import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.web.constants import ACCOUNT_CONSOLE_PATH, ACCOUNT_PATH, LOGIN_PATH
from skat.web.lobby import LOBBY_EVENTS_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import ISSUER_END_SESSION_URL, LEGAL_LINKS, NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.kit_words import kit_text
from tests.e2e.support.lobby_stream import open_table_answer, serve_streams_in_turn, stream_of
from tests.e2e.support.people import DESKTOP, FORM_FACTORS, WIDTHS
from tests.e2e.support.table_menu import open_account_panel
from tests.e2e.support.tables import open_new_table
from tests.support.sign_in_settings import TEST_ISSUER

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

ACCOUNT_ROUTE = f"**{ACCOUNT_PATH}"
UNAUTHORIZED = 401
APP_NAME = text(SOURCE_LANGUAGE, "app.name")
ACCOUNT = text(SOURCE_LANGUAGE, "account.title")
LOG_OUT = kit_text("account.logOut")
LEGAL = kit_text("legalLinks.name")


def open_start_page(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], **options: Any
) -> Page:
    person = record_page_errors(open_person(**options), page_errors)
    person.goto(f"{e2e_server.base_url}/")
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    return person


def account_button(person: Page) -> Locator:
    return person.get_by_role("button", name=ACCOUNT, exact=True)


def wordmark(person: Page) -> Locator:
    return person.get_by_text(APP_NAME, exact=True)


def lull_line(person: Page) -> Locator:
    return person.get_by_role("status").filter(has_text=text(SOURCE_LANGUAGE, "lobby.nobodyPlays"))


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_until_the_lobby_answers_the_page_shows_the_account_button_and_neither_wordmark_nor_new_table_button(
    open_person: Callable[..., Page], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    waiting = open_person(**form_factor)
    # The lobby's stream stays unanswered, so this page is the one a person sees before the lobby has answered.
    waiting.route(f"**{LOBBY_EVENTS_PATH}", lambda _route: None)

    waiting.goto(f"{e2e_server.base_url}/")

    expect(account_button(waiting)).to_be_visible()
    expect(wordmark(waiting)).to_have_count(0)
    expect(waiting.get_by_role("button", name=NEW_TABLE_BUTTON)).to_have_count(0)
    expect(lull_line(waiting)).to_have_count(0)
    expect(waiting.get_by_role("heading")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_no_open_table_the_start_page_says_that_nobody_plays_and_offers_a_new_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    serve_streams_in_turn(person, [stream_of(open_tables=[])])

    person.goto(f"{e2e_server.base_url}/")

    expect(lull_line(person)).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(person.get_by_role("heading")).to_have_count(0)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_lobby_stream_that_fails_on_first_load_shows_the_reconnect_line_and_no_button_until_it_answers(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    answering = False

    def answer(route: Route) -> None:
        if answering:
            route.continue_()
        else:
            route.abort()

    person.route(f"**{LOBBY_EVENTS_PATH}", answer)

    person.goto(f"{e2e_server.base_url}/")

    line = person.get_by_role("status").filter(has_text=text(SOURCE_LANGUAGE, "app.reconnecting"))
    expect(line).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_have_count(0)
    answering = True
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(line).to_have_count(0)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_table_opening_on_the_empty_page_changes_the_scene_to_the_lobby(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    serve_streams_in_turn(
        person,
        [stream_of(open_tables=[]), stream_of(open_tables=[open_table_answer("Ina", names=("Ina", None, None))])],
    )

    person.goto(f"{e2e_server.base_url}/")

    expect(person.get_by_role("heading", name=text(SOURCE_LANGUAGE, "lobby.title", name="Ina"))).to_be_visible()
    expect(lull_line(person)).to_have_count(0)
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_start_page_shows_the_wordmark_the_account_button_and_the_new_table_button(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)

    expect(person).to_have_title(APP_NAME)
    expect(wordmark(person)).to_be_visible()
    expect(account_button(person)).to_be_visible()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_account_button_shows_the_initial_of_the_accounts_name(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="felix.hummert", **form_factor), page_errors)

    person.goto(f"{e2e_server.base_url}/")

    expect(account_button(person).get_by_text("F", exact=True)).to_be_visible()


def open_the_start_pages_account_menu(person: Page, e2e_server: RunningServer) -> Page:
    """The start page with its account menu open, whose rows are found on the page itself."""
    person.goto(f"{e2e_server.base_url}/")
    account_button(person).click()
    return person


def open_the_table_menus_account_menu(person: Page, e2e_server: RunningServer) -> Locator:
    open_new_table(person, e2e_server)
    return open_account_panel(person)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(
    "open_account_menu",
    [open_the_start_pages_account_menu, open_the_table_menus_account_menu],
    ids=["start page", "table page"],
)
def test_the_account_menu_holds_the_username_one_log_out_and_the_legal_row_and_the_page_no_legal_footer(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    open_account_menu: Callable[[Page, RunningServer], Page | Locator],
) -> None:
    person = record_page_errors(open_person(username="felix.hummert", **form_factor), page_errors)

    menu = open_account_menu(person, e2e_server)

    expect(menu.get_by_role("link", name="felix.hummert", exact=True)).to_be_visible()
    expect(menu.get_by_role("button", name=LOG_OUT)).to_have_count(1)
    legal = menu.get_by_role("navigation", name=LEGAL)
    expect(legal.get_by_role("link")).to_have_count(len(LEGAL_LINKS))
    for key, href in LEGAL_LINKS.items():
        expect(legal.get_by_role("link", name=text(SOURCE_LANGUAGE, key))).to_have_attribute("href", href)
    expect(person.get_by_role("navigation", name=LEGAL)).to_have_count(1)


def test_the_menu_closes_on_escape_and_on_a_press_outside(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **DESKTOP)

    log_out = person.get_by_role("button", name=LOG_OUT)

    account_button(person).click()
    expect(log_out).to_be_visible()
    person.keyboard.press("Escape")
    expect(log_out).to_be_hidden()

    account_button(person).click()
    expect(log_out).to_be_visible()
    person.mouse.click(10, 400)
    expect(log_out).to_be_hidden()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(
    "open_account_menu",
    [open_the_start_pages_account_menu, open_the_table_menus_account_menu],
    ids=["start page", "table page"],
)
def test_the_name_opens_the_account_console_in_a_new_tab_and_closes_the_menu(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    open_account_menu: Callable[[Page, RunningServer], Page | Locator],
) -> None:
    expected_request_failures.append(TEST_ISSUER)
    person = record_page_errors(open_person(username="felix.hummert", **form_factor), page_errors)
    console_answers: list[tuple[int, str | None]] = []
    person.context.on(
        "response",
        lambda response: (
            console_answers.append((response.status, response.header_value("location")))
            if urlsplit(response.url).path == ACCOUNT_CONSOLE_PATH
            else None
        ),
    )
    menu = open_account_menu(person, e2e_server)
    name_row = menu.get_by_role("link", name="felix.hummert", exact=True)
    expect(name_row).to_have_attribute("target", "_blank")

    with person.context.expect_event("page"):
        name_row.click()

    expect(menu.get_by_role("button", name=LOG_OUT)).to_be_hidden()
    assert console_answers[0] == (303, f"{TEST_ISSUER}/account")


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_account_button_and_menu_speak_german(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)

    account_button(person).click()

    expect(person.get_by_role("button", name=LOG_OUT)).to_be_visible()
    expect(person.get_by_role("document")).to_have_attribute("lang", SOURCE_LANGUAGE)


def test_a_menu_the_account_cannot_name_is_called_account_and_still_logs_out(
    open_person: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = open_person(**DESKTOP)
    person.route(ACCOUNT_ROUTE, lambda route: route.fulfill(status=500, body="{}"))

    person.goto(f"{e2e_server.base_url}/")
    account_button(person).click()

    expect(person.get_by_role("link", name=ACCOUNT, exact=True)).to_be_visible()
    expect(person.get_by_role("button", name=LOG_OUT)).to_be_visible()


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
    account_button(person).click()

    person.get_by_role("button", name=LOG_OUT).click()

    expect(person.get_by_role("link", name=kit_text("signIn.logIn"), exact=True)).to_be_visible()
    assert urlsplit(person.url).path == LOGIN_PATH
    assert len(end_session_posts) == 1
    assert e2e_server.stores.sessions.load(session_id) is None
    assert [cookie for cookie in person.context.cookies() if cookie["name"].startswith("__Host-")] == []
