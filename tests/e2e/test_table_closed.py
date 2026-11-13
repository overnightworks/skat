import json
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, Route, expect
from sqlalchemy import select, update

from skat.store.schema import tables
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import (
    assert_never_reloaded,
    click_new_table,
    mark_page,
    open_new_table,
    sit_in,
    table_id_of,
    until_the_agents_are_read,
    watch,
    watchers_of,
)
from tests.support.signed_in import new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

EMPTY_TABLE_SECONDS = 2
ENDS_WITHIN_SECONDS = EMPTY_TABLE_SECONDS + 20
UNPLAYED_DAYS = 2
# How often the server looks for dealt tables nobody has played at for the days; the hour of a real run is no wait.
UNPLAYED_SWEEP_SECONDS = 1
POLL_SECONDS = 0.2
# The wait of a browser's stream before it asks again, with room to spare.
RECONNECT_WINDOW_MILLISECONDS = 6_000
# The scenes `s3-idle` and `s3-missing` name the wait and the table in these words.
CLOSED_HEADING = text(SOURCE_LANGUAGE, "closed.emptySeconds", count=EMPTY_TABLE_SECONDS)
UNPLAYED_HEADING = text(SOURCE_LANGUAGE, "closed.unplayedDays", count=UNPLAYED_DAYS)
NOT_FOUND_HEADING = "Tisch nicht gefunden"
UNKNOWN_ID = "0" * 32


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, with an empty-table wait and a sweep for unplayed tables short enough to wait out."""
    with skat_on_new_database(
        tmp_path_factory,
        unplayed_sweep_seconds=UNPLAYED_SWEEP_SECONDS,
        empty_table_seconds=EMPTY_TABLE_SECONDS,
        paused_table_days=UNPLAYED_DAYS,
    ) as server:
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
    """The requests for a table's stream; the start page's own list stream is none of them."""
    requests: list[str] = []

    def record(request: Request) -> None:
        path = urlsplit(request.url).path
        if path.startswith(f"{TABLES_PATH}/") and path.endswith(TABLE_EVENTS_SUFFIX):
            requests.append(request.url)

    person.on("request", record)
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


def played_longer_ago_than_the_days(server: RunningServer, table_id: str) -> None:
    last_play = datetime.now(UTC) - timedelta(days=UNPLAYED_DAYS + 1)
    with server.engine.begin() as connection:
        connection.execute(update(tables).where(tables.c.id == table_id).values(last_played_at=last_play))


def watch_until_the_agents_are_read(person: Page, server: RunningServer, path: str) -> None:
    with until_the_agents_are_read(person):
        watch(person, server, path)


def expect_the_unplayed_face(person: Page) -> None:
    expect(person.get_by_role("heading", name=UNPLAYED_HEADING)).to_be_visible(timeout=ENDS_WITHIN_SECONDS * 1000)
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    for absent in (text(SOURCE_LANGUAGE, "table.sitDown"), text(SOURCE_LANGUAGE, "table.reconnecting")):
        expect(person.get_by_text(absent)).to_be_hidden()
    expect_the_panel_inside_the_viewport(person)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_dealt_table_nobody_played_at_for_the_days_shows_its_end_to_every_open_page_and_on_its_old_link(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    anna, ben, cleo, dora, erik = (
        record_page_errors(open_person(username=name, **form_factor), page_errors)
        for name in ("anna", "ben", "cleo", "dora", "erik")
    )
    path = open_new_table(anna, e2e_server)
    for seat, person in ((2, ben), (3, cleo)):
        watch_until_the_agents_are_read(person, e2e_server, path)
        sit_in(person, seat)
    watch_until_the_agents_are_read(dora, e2e_server, path)
    expect(anna.locator(".card-face").first).to_be_visible()
    open_pages = (anna, ben, cleo, dora)
    # A page asks for the table's agents when its stream brings its first table; the table ends only after all have.
    for person in open_pages:
        expect(watchers_of(person)).to_have_text("1")
    for person in open_pages:
        mark_page(person)

    played_longer_ago_than_the_days(e2e_server, table_id_of(path))

    for person in open_pages:
        expect_the_unplayed_face(person)
    assert_never_reloaded(*open_pages)
    old_link = f"{e2e_server.base_url}{path}"
    # The coverage collector answers a goto of a page that runs the app with a 204, so a page at the link reloads it.
    for person, open_old_link in (
        (anna, anna.reload),
        (dora, dora.reload),
        (erik, lambda: erik.goto(old_link)),
    ):
        requests = events_requests_of(person)
        open_old_link()
        expect_the_unplayed_face(person)
        assert requests == []
