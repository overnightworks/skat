import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Locator, Page, Route, expect

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
from tests.e2e.support.lobby_stream import EVENT_STREAM, open_table_answer, serve_streams_in_turn, stream_of
from tests.e2e.support.people import DESKTOP, FORM_FACTORS, PHONE, WIDTHS
from tests.e2e.support.style import in_the_scene
from tests.e2e.support.table_menu import open_account_panel
from tests.e2e.support.tables import open_new_table
from tests.support.sign_in_settings import TEST_ISSUER

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

START_SCENES = Path(__file__).parents[2] / "docs" / "mockups" / "start.html"
# The scene frame that stands for the empty page at each width; the scenes draw the empty page at 390 and 1280 px only.
EMPTY_SCENE_FRAMES = {360: "lobby-open-360", 390: "s3-empty-390", 1280: "s3-empty-1280"}

ACCOUNT_ROUTE = f"**{ACCOUNT_PATH}"
UNAUTHORIZED = 401
START_WORDMARK = ".start-wordmark"
START_PIPS = ".start-pips span"
ACCOUNT_NAME = ".account-name"
ACCOUNT_AVATAR_FACE = ".account-avatar"
# One jack of each suit.
FOUR_JACKS = 4
# The lobby scene draws one sticky bar at the screen's foot; its button ends in the lowest quarter.
LOWEST_QUARTER = 0.75


def open_start_page(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], **options: Any
) -> Page:
    person = record_page_errors(open_person(**options), page_errors)
    person.goto(f"{e2e_server.base_url}/")
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    return person


def box_of(locator: Locator) -> dict[str, float]:
    box = locator.bounding_box()
    assert box is not None
    return box


def drawn_boxes(person: Page) -> list[dict[str, float]]:
    """The boxes of the account button and its avatar, which both scenes draw."""
    return [box_of(element) for element in person.locator(".account-button, .account-avatar").all()]


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_until_the_lobby_answers_the_page_draws_the_account_button_and_neither_wordmark_nor_button(
    open_person: Callable[..., Page], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    waiting = open_person(**form_factor)
    # The lobby's stream stays unanswered, so this page is the one a person sees before the lobby has answered.
    waiting.route(f"**{LOBBY_EVENTS_PATH}", lambda _route: None)

    waiting.goto(f"{e2e_server.base_url}/")

    expect(waiting.locator(ACCOUNT_AVATAR)).to_be_visible()
    expect(waiting.locator(f"{START_WORDMARK}, {START_PIPS}")).to_have_count(0)
    expect(waiting.get_by_role("button", name=NEW_TABLE_BUTTON)).to_have_count(0)
    expect(waiting.locator(".start-table, .lobby-lists")).to_have_count(0)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize("scene", ["empty", "open"])
def test_nothing_drawn_before_the_lobby_answers_moves_when_the_first_answer_arrives(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
    scene: str,
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    held: list[Route] = []
    person.route(f"**{LOBBY_EVENTS_PATH}", lambda route: held.append(route))
    with person.expect_request(f"**{LOBBY_EVENTS_PATH}"):
        person.goto(f"{e2e_server.base_url}/")
    # The account's name arrives on its own read, apart from the lobby's answer.
    expect(person.locator(".account-name")).to_have_count(1)
    person.evaluate("document.fonts.ready.then(() => true)")
    before = drawn_boxes(person)
    assert before

    tables = [] if scene == "empty" else [open_table_answer("Ina", names=("Ina", None, None))]
    held[0].fulfill(status=200, headers={"content-type": EVENT_STREAM}, body=stream_of(open_tables=tables))
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(person.locator(START_WORDMARK)).to_be_visible()
    person.evaluate("document.fonts.ready.then(() => true)")

    assert drawn_boxes(person) == before


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_no_open_table_the_start_page_draws_the_table_the_lull_line_the_jacks_and_the_button_on_the_felt(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    serve_streams_in_turn(person, [stream_of(open_tables=[])])

    person.goto(f"{e2e_server.base_url}/")

    table = person.locator(".start-table")
    lull = person.get_by_role("status").filter(has_text=text(SOURCE_LANGUAGE, "lobby.nobodyPlays"))
    expect(lull).to_be_visible()
    expect(person.locator(".start-chair")).to_have_count(2)
    expect(person.locator(".start-jack")).to_have_count(FOUR_JACKS)
    assert (
        person.locator(".start-jack .card-face").evaluate_all("faces => faces.map(face => face.dataset.rank)")
        == ["jack"] * FOUR_JACKS
    )
    expect(person.locator(".lobby-lists")).to_have_count(0)
    button = person.get_by_role("button", name=NEW_TABLE_BUTTON)
    expect(button).to_be_visible()
    table_box, lull_box, button_box = box_of(table), box_of(lull), box_of(button)
    jacks_bottom = max(box["y"] + box["height"] for box in map(box_of, person.locator(".start-jack").all()))
    assert table_box["x"] <= button_box["x"]
    assert table_box["y"] <= button_box["y"]
    assert button_box["y"] + button_box["height"] <= table_box["y"] + table_box["height"]
    assert button_box["x"] + button_box["width"] <= table_box["x"] + table_box["width"]
    assert abs(button_box["x"] + button_box["width"] / 2 - (table_box["x"] + table_box["width"] / 2)) <= 1
    assert lull_box["y"] + lull_box["height"] <= button_box["y"]
    assert jacks_bottom <= button_box["y"]
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_no_open_table_the_start_page_paints_its_backdrop_as_the_scene_does(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    serve_streams_in_turn(person, [stream_of(open_tables=[])])
    person.goto(f"{e2e_server.base_url}/")
    expect(person.locator(".start-table")).to_be_visible()
    frame = EMPTY_SCENE_FRAMES[form_factor["viewport"]["width"]]
    scenes = person.context.new_page()
    try:
        scenes.goto(f"{START_SCENES.as_uri()}?f={frame}")
        drawn = scenes.locator(f"[id='{frame}']").evaluate("frame => getComputedStyle(frame).backgroundImage")
    finally:
        scenes.close()

    assert person.locator(".start").evaluate("page => getComputedStyle(page).backgroundImage") == drawn


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_table_page_paints_the_same_wood_backdrop_as_its_scene(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    person = open_person(**form_factor)
    open_new_table(person, e2e_server)
    expect(person.locator(".room")).to_be_visible()

    drawn = in_the_scene(person, "skat-choose", "frame => getComputedStyle(frame).backgroundImage", None)

    assert person.locator(".room").evaluate("page => getComputedStyle(page).backgroundImage") == drawn


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_open_tables_list_sits_where_the_lobby_scene_draws_it(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    tables = [open_table_answer(opener, names=(opener, None, None)) for opener in ("Ina", "Jan", "Kim")]
    serve_streams_in_turn(person, [stream_of(open_tables=tables)])
    person.goto(f"{e2e_server.base_url}/")
    expect(person.locator(".lobby-card")).to_have_count(len(tables))
    person.evaluate("document.fonts.ready.then(() => true)")
    drawn = [box_of(person.locator(".lobby-lists h2")), box_of(person.locator(".lobby-card").first)]
    frame = f"lobby-open-{form_factor['viewport']['width']}"
    scenes = person.context.new_page()
    try:
        scenes.goto(f"{START_SCENES.as_uri()}?f={frame}")
        origin = box_of(scenes.locator(f"[id='{frame}']"))
        scene = [
            box_of(scenes.locator(f"[id='{frame}'] .section-head")),
            box_of(scenes.locator(f"[id='{frame}'] .entry").first),
        ]
    finally:
        scenes.close()

    assert [box["y"] for box in drawn] == pytest.approx([box["y"] - origin["y"] for box in scene], abs=1)


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
    button = person.get_by_role("button", name=NEW_TABLE_BUTTON)
    expect(button).to_be_visible()
    expect(line).to_have_count(0)
    person.evaluate("document.fonts.ready.then(() => true)")
    arrived = box_of(button)
    person.reload()
    expect(button).to_be_visible()
    person.evaluate("document.fonts.ready.then(() => true)")
    assert arrived == box_of(button)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize("scene", ["empty", "open"])
def test_the_new_table_button_keeps_its_place_while_its_scene_stays_the_same(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
    scene: str,
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(**form_factor)
    one = [open_table_answer("Ina", names=("Ina", None, None))]
    three = [
        *one,
        open_table_answer("Jan", names=("Jan", "Jo", None)),
        open_table_answer("Kim", names=("Kim", None, None)),
    ]
    first, then = ([], []) if scene == "empty" else (one, three)
    serve_streams_in_turn(person, [stream_of(open_tables=first), stream_of(open_tables=then)])

    person.goto(f"{e2e_server.base_url}/")
    button = person.get_by_role("button", name=NEW_TABLE_BUTTON)
    expect(button).to_be_visible()
    # A web font that arrives later widens the label, which is no move of the scene.
    person.evaluate("document.fonts.ready.then(() => true)")
    before = box_of(button)
    # The first stream ends with its list: the page shows the lost line, then the next list arrives.
    expect(person.get_by_role("status").filter(has_text=text(SOURCE_LANGUAGE, "app.reconnecting"))).to_be_visible()
    if scene == "open":
        expect(person.locator(".lobby-card")).to_have_count(len(three))

    assert box_of(button) == before


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_table_opening_on_the_empty_page_changes_the_scene_to_the_lobby_with_the_button_at_the_foot(
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

    expect(person.locator(".lobby-card")).to_have_count(1)
    expect(person.locator(".start-table")).to_have_count(0)
    box = box_of(person.get_by_role("button", name=NEW_TABLE_BUTTON))
    assert box["y"] + box["height"] >= form_factor["viewport"]["height"] * LOWEST_QUARTER


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_start_page_shows_the_wordmark_the_account_button_and_the_new_table_button(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = open_start_page(open_person, e2e_server, page_errors, **form_factor)

    expect(person).to_have_title(text(SOURCE_LANGUAGE, "app.name"))
    expect(person.locator(START_WORDMARK)).to_have_text(text(SOURCE_LANGUAGE, "app.name"))
    expect(person.locator(ACCOUNT_AVATAR)).to_be_visible()
    expect(person.locator("body")).to_have_css("margin", "0px")
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize(("form_factor", "name_shown"), [(DESKTOP, True), (PHONE, False)], ids=["desktop", "phone"])
def test_the_start_page_head_centres_the_wordmark_over_four_suits_and_shows_the_account_as_avatar_with_name_on_desktop(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    name_shown: bool,
) -> None:
    person = record_page_errors(open_person(username="felix.hummert", **form_factor), page_errors)
    person.goto(f"{e2e_server.base_url}/")
    expect(person.locator(ACCOUNT_AVATAR_FACE)).to_have_text("F")

    wordmark = person.locator(START_WORDMARK).bounding_box()
    assert wordmark is not None
    assert abs(wordmark["x"] + wordmark["width"] / 2 - form_factor["viewport"]["width"] / 2) <= 1
    mark_top = person.evaluate(
        "parseFloat(getComputedStyle(document.querySelector('.start-head')).getPropertyValue('--mark-top'))"
    )
    assert abs(wordmark["y"] - mark_top) <= 1
    expect(person.locator(START_PIPS)).to_have_count(4)
    expect(person.locator(ACCOUNT_NAME)).to_be_visible(visible=name_shown)
    if name_shown:
        expect(person.locator(ACCOUNT_NAME)).to_have_text("felix.hummert")


def test_the_start_page_head_shows_a_person_mark_in_the_avatar_while_the_account_is_unnamed(
    open_person: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = open_person(**DESKTOP)
    person.route(ACCOUNT_ROUTE, lambda route: route.fulfill(status=500, body="{}"))
    person.goto(f"{e2e_server.base_url}/")

    expect(person.locator(ACCOUNT_AVATAR_FACE).locator("svg")).to_be_visible()
    expect(person.locator(ACCOUNT_NAME)).to_have_count(0)


def open_the_start_pages_account_menu(person: Page, e2e_server: RunningServer) -> Locator:
    person.goto(f"{e2e_server.base_url}/")
    person.locator(ACCOUNT_AVATAR).click()
    return person.locator(ACCOUNT_MENU)


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
    open_account_menu: Callable[[Page, RunningServer], Locator],
) -> None:
    person = record_page_errors(open_person(username="felix.hummert", **form_factor), page_errors)

    menu = open_account_menu(person, e2e_server)

    expect(menu.get_by_role("link").first).to_have_text("felix.hummert")
    expect(menu.get_by_role("button", name=kit_text("account.logOut"))).to_have_count(1)
    assert {(link.inner_text(), link.get_attribute("href")) for link in menu.locator("nav a").all()} == {
        (text(SOURCE_LANGUAGE, key), href) for key, href in LEGAL_LINKS.items()
    }
    expect(person.locator("nav.legal")).to_have_count(1)


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
    open_account_menu: Callable[[Page, RunningServer], Locator],
) -> None:
    expected_request_failures.append(TEST_ISSUER)
    person = record_page_errors(open_person(**form_factor), page_errors)
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
    name_row = menu.get_by_role("link").first
    expect(name_row).to_have_attribute("target", "_blank")

    with person.context.expect_event("page"):
        name_row.click()

    expect(menu).to_be_hidden()
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
