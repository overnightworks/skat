import json
import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect
from sqlalchemy import select

from skat.store.schema import tables
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.table_menu import menu_button
from tests.e2e.support.tables import (
    RECONNECT_MILLISECONDS,
    assert_never_reloaded,
    mark_page,
    open_new_table,
    watch,
)
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
RECONNECTING = text(SOURCE_LANGUAGE, "table.reconnecting")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
CLOSED_HEADING = text(SOURCE_LANGUAGE, "closed.emptySeconds", count=EMPTY_TABLE_SECONDS)
NOT_FOUND_HEADING = text(SOURCE_LANGUAGE, "closed.notFound")


# its own settings: this file's constants differ from the other file's, whose fixture reads the same
@pytest.fixture(scope="module")
def ended_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """A Skat whose empty table ends after a short wait, so that one table can end within the test."""
    with skat_on_new_database(tmp_path_factory, empty_table_seconds=EMPTY_TABLE_SECONDS) as server:
        yield server


# waits for this file's own ENDS_WITHIN_SECONDS, which the other file's copy reads as its own constant
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


def lobby_of(person: Page, name: str = LOBBY) -> Locator:
    """The lobby button by its whole name, which counts the person's other tables that wait for him."""
    return person.get_by_role("link", name=name, exact=True)


def expect_the_lobby_to_take_the_person_to_the_start_page(person: Page, base_url: str) -> None:
    lobby_of(person).click()
    expect(person).to_have_url(f"{base_url}/")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_seated_table_offers_the_lobby_button_as_its_bars_only_link(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)

    open_new_table(person, e2e_server)

    expect(lobby_of(person)).to_have_attribute("href", "/")
    expect(person.get_by_role("banner").get_by_role("link")).to_have_count(1)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_takes_the_seated_person_home_and_keeps_the_seat(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(person, e2e_server)

    expect_the_lobby_to_take_the_person_to_the_start_page(person, e2e_server.base_url)
    person.go_back()

    expect(person).to_have_url(f"{e2e_server.base_url}{path}")
    expect(menu_button(person, STAND_UP)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_takes_the_person_home_while_the_page_reconnects(
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
    expect_the_lobby_to_take_the_person_to_the_start_page(person, e2e_server.base_url)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_of_a_dealt_table_takes_the_declarer_home(
    deal_a_declaring_table: Callable[..., Any], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)

    expect_the_lobby_to_take_the_person_to_the_start_page(table.declarer, e2e_server.base_url)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_lobby_button_of_a_missing_table_takes_the_person_home(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors, console=False)

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{UNKNOWN_ID}")

    expect(person.get_by_role("heading", name=NOT_FOUND_HEADING)).to_be_visible()
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
    expect_the_lobby_to_take_the_person_to_the_start_page(person, ended_server.base_url)


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
    expect(lobby_of(person)).to_be_visible()

    deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))

    expect(lobby_of(person, LOBBY_WAITING_ONE).get_by_text("1", exact=True)).to_be_visible()
    assert_never_reloaded(person)

    deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))

    expect(lobby_of(person, LOBBY_WAITING_TWO).get_by_text("2", exact=True)).to_be_visible()


def test_the_table_the_person_is_at_is_never_counted_even_when_it_waits_for_him(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    person = record_page_errors(open_person(**PHONE), page_errors)
    table_id = deal_a_table_that_waits_for(e2e_server, RawSession(e2e_server, member_of(person)))

    watch(person, e2e_server, f"{TABLE_PAGE_PREFIX}{table_id}")

    expect(lobby_of(person)).to_be_visible()


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
    expect(lobby_of(person)).to_be_visible()
    person.unroute(events, count_one_then_end_and_refuse_the_rest)

    expect(lobby_of(person, LOBBY_WAITING_ONE)).to_be_visible(timeout=RECONNECT_MILLISECONDS)
    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_have_count(0)
