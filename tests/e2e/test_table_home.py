import json
import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect
from sqlalchemy import select

from skat.store.schema import tables
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import RECONNECT_MILLISECONDS, assert_never_reloaded, mark_page, open_new_table
from tests.e2e.support.waiting_tables import deal_a_table_that_waits_for
from tests.support.signed_in import new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

EMPTY_TABLE_SECONDS = 2
ENDS_WITHIN_SECONDS = EMPTY_TABLE_SECONDS + 20
POLL_SECONDS = 0.2
UNKNOWN_ID = "0" * 32
LOBBY = text(SOURCE_LANGUAGE, "table.lobby")
LOBBY_WAITING_ONE = text(SOURCE_LANGUAGE, "table.lobbyWaiting", count=1)
LOBBY_WAITING_TWO = text(SOURCE_LANGUAGE, "table.lobbyWaiting", count=2)
OTHER_TABLES_BEYOND_THE_CAP = 10
RECONNECTING = text(SOURCE_LANGUAGE, "table.reconnecting")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
CLOSED_HEADING = text(SOURCE_LANGUAGE, "closed.emptySeconds", count=EMPTY_TABLE_SECONDS)
NOT_FOUND_HEADING = text(SOURCE_LANGUAGE, "closed.notFound")
# A tap target is at least this many CSS pixels on each side.
TAP_TARGET_PIXELS = 44
TRANSPARENT_COLOR = "rgba(0, 0, 0, 0)"


@pytest.fixture(scope="module")
def ended_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """A Skat whose empty table ends after a short wait, so that one table can end within the test."""
    with skat_on_new_database(tmp_path_factory, empty_table_seconds=EMPTY_TABLE_SECONDS) as server:
        yield server


def wait_for_end(server: RunningServer, table_id: str) -> None:
    deadline = time.monotonic() + ENDS_WITHIN_SECONDS
    while time.monotonic() < deadline:
        with server.engine.connect() as connection:
            if connection.execute(select(tables.c.ended_at).where(tables.c.id == table_id)).scalar_one() is not None:
                return
        time.sleep(POLL_SECONDS)
    pytest.fail(f"table {table_id} did not end")


@pytest.fixture(scope="module")
def ended_table_path(ended_server: RunningServer) -> str:
    """The link of a table nobody ever watched, which ended after the wait."""
    account = new_account(ended_server.stores, ended_server.config)
    member = seed_member(ended_server.stores, ended_server.config, account=account)
    body = {"command_id": "home-ended-create-0001", "series_length": 36}
    created = json.loads(RawSession(ended_server, member).post(TABLES_PATH, body))
    wait_for_end(ended_server, created["id"])
    return f"{TABLE_PAGE_PREFIX}{created['id']}"


def lobby_of(person: Page) -> Any:
    return person.get_by_role("link", name=LOBBY)


def expect_the_lobby_top_left_and_tappable(person: Page) -> None:
    """The button sits in the top left quarter of the page, is a whole tap target, and clears the watchers."""
    expect(lobby_of(person)).to_be_visible()
    box = lobby_of(person).bounding_box()
    viewport = person.viewport_size
    assert box is not None
    assert viewport is not None
    assert box["x"] >= 0
    assert box["x"] + box["width"] <= viewport["width"] / 2
    assert box["y"] + box["height"] <= viewport["height"] / 4
    assert box["width"] >= TAP_TARGET_PIXELS
    assert box["height"] >= TAP_TARGET_PIXELS
    watchers = person.locator(".watchers")
    if watchers.count():
        watchers_box = watchers.bounding_box()
        assert watchers_box is not None
        assert box["x"] + box["width"] <= watchers_box["x"]
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def expect_the_lobby_glass_on_the_wood(person: Page) -> None:
    """The button has a translucent fill and a hairline ring, so the wood shows through it and the ring marks it."""
    face = person.locator(".lobby-face")
    expect(face).not_to_have_css("background-color", TRANSPARENT_COLOR)
    assert face.evaluate("element => getComputedStyle(element).boxShadow.includes('inset')")


def expect_the_lobby_to_take_the_person_to_the_start_page(person: Page, base_url: str) -> None:
    lobby_of(person).click()
    expect(person).to_have_url(f"{base_url}/")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_seated_table_offers_the_lobby_button_top_left_and_no_wordmark_link(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)

    open_new_table(person, e2e_server)

    expect_the_lobby_top_left_and_tappable(person)
    expect_the_lobby_glass_on_the_wood(person)
    expect(person.locator(".bar a")).to_have_count(1)
    expect(lobby_of(person)).to_have_attribute("href", "/")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_takes_the_seated_person_home_and_keeps_the_seat(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(person, e2e_server)

    expect_the_lobby_to_take_the_person_to_the_start_page(person, e2e_server.base_url)
    person.go_back()

    expect(person).to_have_url(f"{e2e_server.base_url}{path}")
    expect(person.get_by_role("button", name=STAND_UP)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_stays_tappable_and_undimmed_while_the_page_reconnects(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    # The stream the test aborts is the console error the browser logs, so only script errors are recorded.
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors, console=False)
    open_new_table(person, e2e_server)
    person.route(f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}", lambda route: route.abort())

    person.reload()

    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    expect_the_lobby_top_left_and_tappable(person)
    expect(lobby_of(person)).to_have_css("pointer-events", "auto")
    expect(lobby_of(person)).to_have_css("filter", "none")
    expect_the_lobby_to_take_the_person_to_the_start_page(person, e2e_server.base_url)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_of_a_dealt_table_takes_the_declarer_home(
    deal_a_declaring_table: Callable[..., Any], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)

    expect_the_lobby_top_left_and_tappable(table.declarer)
    expect_the_lobby_to_take_the_person_to_the_start_page(table.declarer, e2e_server.base_url)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_of_a_missing_table_takes_the_person_home(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors, console=False)

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{UNKNOWN_ID}")

    expect(person.get_by_role("heading", name=NOT_FOUND_HEADING)).to_be_visible()
    expect_the_lobby_top_left_and_tappable(person)
    expect_the_lobby_to_take_the_person_to_the_start_page(person, e2e_server.base_url)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_of_an_ended_table_takes_the_person_home(
    open_person: Callable[..., Page],
    ended_server: RunningServer,
    ended_table_path: str,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    person = record_page_errors(open_person(username="anna", server=ended_server, **form_factor), page_errors)

    person.goto(f"{ended_server.base_url}{ended_table_path}")

    expect(person.get_by_role("heading", name=CLOSED_HEADING)).to_be_visible()
    expect_the_lobby_top_left_and_tappable(person)
    expect_the_lobby_to_take_the_person_to_the_start_page(person, ended_server.base_url)


def badge_of(person: Page) -> Any:
    return person.locator(".lobby-badge")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_that_waits_for_the_person_puts_its_number_on_the_lobby_button_while_he_plays_here(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    person = record_page_errors(open_person(**form_factor), page_errors)
    open_new_table(person, e2e_server)
    mark_page(person)
    expect(badge_of(person)).to_have_count(0)
    expect(lobby_of(person)).to_have_attribute("aria-label", LOBBY)

    deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))

    expect(badge_of(person)).to_have_text("1")
    expect(lobby_of(person)).to_have_attribute("aria-label", LOBBY_WAITING_ONE)
    expect(person.get_by_role("link", name=LOBBY_WAITING_ONE)).to_be_visible()
    face, badge = person.locator(".lobby-face").bounding_box(), badge_of(person).bounding_box()
    assert face is not None
    assert badge is not None
    assert badge["width"] == badge["height"] > 0
    assert badge["x"] <= face["x"] + face["width"] <= badge["x"] + badge["width"]
    assert badge["y"] <= face["y"] <= badge["y"] + badge["height"]
    expect_the_lobby_top_left_and_tappable(person)
    assert_never_reloaded(person)

    deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))

    expect(badge_of(person)).to_have_text("2")
    expect(lobby_of(person)).to_have_attribute("aria-label", LOBBY_WAITING_TWO)


def test_the_table_the_person_is_at_is_never_counted_even_when_it_waits_for_him(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    person = record_page_errors(open_person(**PHONE), page_errors)
    table_id = deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{table_id}")

    expect(person.locator(".chair")).to_have_count(3)
    expect(lobby_of(person)).to_be_visible()
    expect(badge_of(person)).to_have_count(0)


def test_more_than_nine_waiting_tables_read_nine_plus(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    person = record_page_errors(open_person(**PHONE), page_errors)
    open_new_table(person, e2e_server)
    him = RawSession(e2e_server, member_of(person))

    for _ in range(OTHER_TABLES_BEYOND_THE_CAP):
        deal_a_table_that_waits_for(e2e_server, him)

    expect(badge_of(person)).to_have_text("9+")
    expect(lobby_of(person)).to_have_attribute(
        "aria-label", text(SOURCE_LANGUAGE, "table.lobbyWaiting", count=OTHER_TABLES_BEYOND_THE_CAP)
    )


def test_a_lost_stream_hides_the_number_and_the_stream_coming_back_brings_it_again(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    person = record_page_errors(open_person(**PHONE), page_errors, console=False)
    open_new_table(person, e2e_server)
    deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))
    streams: list[str] = []

    def count_one_then_end_and_refuse_the_rest(route: Route) -> None:
        streams.append(route.request.url)
        if len(streams) == 1:
            route.fulfill(content_type="text/event-stream", body="event: attention\ndata: 1\n\n")
        else:
            route.abort()

    # Playwright cannot end a stream that is open, so the reloaded page meets one that carries the count and ends.
    events = f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}"
    person.route(events, count_one_then_end_and_refuse_the_rest)
    person.reload()

    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    expect(badge_of(person)).to_have_count(0)
    expect_the_lobby_top_left_and_tappable(person)
    person.unroute(events, count_one_then_end_and_refuse_the_rest)

    expect(badge_of(person)).to_have_text("1", timeout=RECONNECT_MILLISECONDS)
    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_have_count(0)
