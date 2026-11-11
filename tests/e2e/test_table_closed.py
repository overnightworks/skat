import json
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect
from sqlalchemy import select

from skat.store.schema import tables
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import click_new_table, open_new_table, table_id_of
from tests.support.signed_in import new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

EMPTY_TABLE_SECONDS = 2
ENDS_WITHIN_SECONDS = EMPTY_TABLE_SECONDS + 20
POLL_SECONDS = 0.2
# The wait of a browser's stream before it asks again, with room to spare.
RECONNECT_WINDOW_MILLISECONDS = 6_000
# The scenes `s3-idle` and `s3-missing` name the wait and the table in these words.
CLOSED_HEADING = f"{EMPTY_TABLE_SECONDS} Sekunden niemand da: Tisch geschlossen"
NOT_FOUND_HEADING = "Tisch nicht gefunden"
UNKNOWN_ID = "0" * 32


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, with an empty-table wait short enough to wait out."""
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
def ended_table_path(e2e_server: RunningServer) -> str:
    """The link of a table nobody ever watched, which ended after the wait."""
    member = seed_member(
        e2e_server.stores, e2e_server.config, account=new_account(e2e_server.stores, e2e_server.config)
    )
    created = json.loads(
        RawSession(e2e_server, member).post(TABLES_PATH, {"command_id": "closed-create-0001", "series_length": 36})
    )
    wait_for_end(e2e_server, created["id"])
    return f"{TABLE_PAGE_PREFIX}{created['id']}"


def events_requests_of(person: Page) -> list[str]:
    requests: list[str] = []
    person.on("request", lambda request: requests.append(request.url) if TABLE_EVENTS_SUFFIX in request.url else None)
    return requests


def expect_the_panel_inside_the_viewport(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    panel = person.get_by_role("status").filter(has=person.get_by_role("heading")).bounding_box()
    button = person.get_by_role("button", name=NEW_TABLE_BUTTON).bounding_box()
    width = person.viewport_size["width"] if person.viewport_size else 0
    assert panel is not None
    assert button is not None
    for box in (panel, button):
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= width


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_old_link_of_an_ended_table_shows_the_wait_and_offers_no_seat_and_opens_no_stream(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    ended_table_path: str,
    form_factor: dict[str, Any],
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    requests = events_requests_of(person)

    person.goto(f"{e2e_server.base_url}{ended_table_path}")

    expect(person.get_by_role("heading", name=CLOSED_HEADING)).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(person.locator(".chair")).to_have_count(3)
    for absent in (
        text(SOURCE_LANGUAGE, "table.sitDown"),
        text(SOURCE_LANGUAGE, "table.standUp"),
        text(SOURCE_LANGUAGE, "table.copyLink"),
        text(SOURCE_LANGUAGE, "table.reconnecting"),
    ):
        expect(person.get_by_text(absent)).to_be_hidden()
    expect(person.locator(".watchers")).to_have_count(0)
    expect_the_panel_inside_the_viewport(person)
    assert requests == []


def test_a_page_whose_stream_arrives_after_the_wait_shows_the_closed_face_and_asks_for_no_stream_again(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **PHONE), page_errors)
    held: list[Route] = []
    wait_is_up: list[bool] = []

    def hold_the_stream_until_the_wait_is_up(route: Route) -> None:
        if wait_is_up:
            route.continue_()
        else:
            held.append(route)

    requests = events_requests_of(person)
    person.route(f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}", hold_the_stream_until_the_wait_is_up)
    path = open_new_table(person, e2e_server)
    expect(person.locator(".chair")).to_have_count(3)
    wait_for_end(e2e_server, table_id_of(path))
    wait_is_up.append(True)

    for route in held:
        route.continue_()

    expect(person.get_by_role("heading", name=CLOSED_HEADING)).to_be_visible()
    expect(person.get_by_text(text(SOURCE_LANGUAGE, "table.reconnecting"))).to_be_hidden()
    person.wait_for_timeout(RECONNECT_WINDOW_MILLISECONDS)
    assert len(requests) == 1


def test_a_new_table_opens_from_the_closed_face(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], ended_table_path: str
) -> None:
    person = record_page_errors(open_person(username="anna", **PHONE), page_errors)
    person.goto(f"{e2e_server.base_url}{ended_table_path}")

    click_new_table(person)

    expect(person.get_by_text(text(SOURCE_LANGUAGE, "table.waitingForPlayers"))).to_be_visible()
    assert urlsplit(person.url).path != ended_table_path


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_new_table_sheet_dims_the_whole_page_over_the_closed_face(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    ended_table_path: str,
    form_factor: dict[str, Any],
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    person.goto(f"{e2e_server.base_url}{ended_table_path}")

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    scrim = person.locator(".scrim").bounding_box()
    viewport = person.viewport_size
    assert scrim is not None
    assert viewport is not None
    assert (scrim["x"], scrim["y"], scrim["width"], scrim["height"]) == (0, 0, viewport["width"], viewport["height"])


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_new_table_sheet_over_the_closed_face_lays_its_two_buttons_side_by_side(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    ended_table_path: str,
    form_factor: dict[str, Any],
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    person.goto(f"{e2e_server.base_url}{ended_table_path}")

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    confirm, cancel = person.evaluate(
        "() => [...document.querySelectorAll('.sheet .btns button')].map(b => b.getBoundingClientRect().toJSON())"
    )
    assert confirm["right"] <= cancel["left"]
    assert confirm["top"] == pytest.approx(cancel["top"])


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_link_whose_table_is_gone_shows_the_card_back_and_offers_a_new_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors, console=False)

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{UNKNOWN_ID}")

    expect(person.get_by_role("heading", name=NOT_FOUND_HEADING)).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(person.locator(".card-back")).to_be_visible()
    expect(person.locator(".chair")).to_have_count(0)
    expect_the_panel_inside_the_viewport(person)
