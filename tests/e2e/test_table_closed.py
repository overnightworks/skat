import json
import re
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Request, Route, expect
from sqlalchemy import delete, select, update

from skat.store.game_list import append_game_list
from skat.store.schema import metadata, tables
from skat.table.records import OccupantKind
from skat.web.closing import TABLE_CLOSE_SUFFIX
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.settings import DEFAULT_ENDED_TABLE_DAYS
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
    watch_until_the_agents_are_read,
    watchers_of,
)
from tests.support.played_game import an_entry
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
NOT_FOUND_HEADING = text(SOURCE_LANGUAGE, "closed.notFound")
GAME_LIST = ".game-list"
SHEET_BACK = text(SOURCE_LANGUAGE, "table.sheetBack")
# A point of the room outside the centred panel, where a tap lands on the backdrop of the game sheet.
BESIDE_THE_PANEL = (4, 4)
TOO_MANY_STREAMS = text(SOURCE_LANGUAGE, "table.tooManyStreams")
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


def forget_table(server: RunningServer, table_id: str) -> None:
    """Removes the table and everything stored for it, the way the server's own forgetting of an old table does."""
    with server.engine.begin() as connection:
        for stored in reversed(metadata.sorted_tables):
            if stored is not tables and "table_id" in stored.c:
                connection.execute(delete(stored).where(stored.c.table_id == table_id))
        connection.execute(delete(tables).where(tables.c.id == table_id))


def test_a_page_whose_table_is_forgotten_while_it_watches_learns_it_from_its_failed_stream_and_shows_it_gone(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    # The 404s the browser logs for the stream and its probe are the console errors, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **PHONE), page_errors, console=False)
    held: list[Route] = []

    def hold_the_stream(route: Route) -> None:
        if route.request.resource_type == "eventsource":
            held.append(route)
        else:
            route.continue_()

    person.route(f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}", hold_the_stream)
    path = open_new_table(person, e2e_server)
    expect(person.locator(".chair")).to_have_count(3)
    forget_table(e2e_server, table_id_of(path))

    for route in held:
        route.abort()

    expect(person.get_by_role("heading", name=NOT_FOUND_HEADING)).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(person.get_by_text(text(SOURCE_LANGUAGE, "table.reconnecting"))).to_be_hidden()
    expect_the_panel_inside_the_viewport(person)


def test_a_page_whose_account_holds_as_many_streams_as_it_may_says_so_and_keeps_the_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    # The 429s the browser logs for the stream and its probe are the console errors, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **PHONE), page_errors, console=False)
    held: list[Route] = []

    def hold_the_stream(route: Route) -> None:
        if route.request.resource_type == "eventsource":
            held.append(route)
        else:
            route.continue_()

    events = f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}"
    person.route(events, hold_the_stream)
    open_new_table(person, e2e_server)
    expect(person.locator(".chair")).to_have_count(3)
    person.route(events, lambda route: route.fulfill(status=HTTPStatus.TOO_MANY_REQUESTS))

    for route in held:
        route.abort()

    expect(person.get_by_text(TOO_MANY_STREAMS)).to_be_visible()
    expect(person.locator(".chair")).to_have_count(3)


def played_longer_ago_than_the_days(server: RunningServer, table_id: str) -> None:
    last_play = datetime.now(UTC) - timedelta(days=UNPLAYED_DAYS + 1)
    with server.engine.begin() as connection:
        connection.execute(update(tables).where(tables.c.id == table_id).values(last_played_at=last_play))


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


@pytest.fixture(scope="module")
def retained_table(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[RunningServer, str, str]]:
    """A Skat with the link of a closed table that has a game and ended longer ago than the days, as it stands after
    the start's sweep, and the name its closer had.
    """
    with skat_on_new_database(tmp_path_factory) as server:
        opener = RawSession(
            server, seed_member(server.stores, server.config, account=new_account(server.stores, server.config))
        )
        table_id = json.loads(opener.post(TABLES_PATH, {"command_id": "retained-create-0001", "series_length": 36}))[
            "id"
        ]
        opener.post(f"{TABLES_PATH}/{table_id}{TABLE_CLOSE_SUFFIX}", {"command_id": "retained-close-0001"})
        with server.engine.begin() as connection:
            append_game_list(connection, table_id, 1, (an_entry(),), datetime.now(UTC))
            connection.execute(
                update(tables)
                .where(tables.c.id == table_id)
                .values(ended_at=tables.c.ended_at - timedelta(days=DEFAULT_ENDED_TABLE_DAYS + 1))
            )
            closer = connection.execute(select(tables.c.closed_by_name).where(tables.c.id == table_id)).scalar_one()
        assert closer

        server.restart(while_stopping=lambda: None)

        with server.engine.connect() as connection:
            assert (
                connection.execute(select(tables.c.closed_by_name).where(tables.c.id == table_id)).scalar_one() is None
            )
        yield server, f"{TABLE_PAGE_PREFIX}{table_id}", closer


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_old_link_of_a_closed_table_with_games_shows_it_closed_without_the_closers_name_once_the_days_are_up(
    open_person: Callable[..., Page],
    page_errors: list[str],
    retained_table: tuple[RunningServer, str, str],
    form_factor: dict[str, Any],
) -> None:
    server, path, closer = retained_table
    person = record_page_errors(open_person(username="anna", server=server, **form_factor), page_errors)

    person.goto(f"{server.base_url}{path}")

    expect(person.get_by_role("heading", name=text(SOURCE_LANGUAGE, "closed.seriesEnded"))).to_be_visible()
    expect(person.get_by_text(closer)).to_have_count(0)
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect_the_panel_inside_the_viewport(person)


GAME_SEATS = ((1, OccupantKind.PERSON), (2, OccupantKind.PERSON), (3, OccupantKind.AGENT))
SEAT_NAMES = ("Anna", "Ben", "Cleo")
AGENT_NAME = SEAT_NAMES[2]


@pytest.fixture(scope="module")
def closed_with_games(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[RunningServer, str, str]]:
    """A Skat with the link of a table its opener closed after three games, one declared from each seat, the third
    seat held by an agent, and the name its closer had.
    """
    with skat_on_new_database(tmp_path_factory) as server:
        opener = RawSession(
            server, seed_member(server.stores, server.config, account=new_account(server.stores, server.config))
        )
        table_id = json.loads(opener.post(TABLES_PATH, {"command_id": "played-create-0001", "series_length": 36}))["id"]
        opener.post(f"{TABLES_PATH}/{table_id}{TABLE_CLOSE_SUFFIX}", {"command_id": "played-close-0001"})
        games = tuple(
            replace(an_entry(), declarer_seat=seat, seat_kinds=tuple(kind for _, kind in GAME_SEATS))
            for seat, _ in GAME_SEATS
        )
        with server.engine.begin() as connection:
            append_game_list(connection, table_id, 1, games, datetime.now(UTC))
            closer = connection.execute(select(tables.c.closed_by_name).where(tables.c.id == table_id)).scalar_one()
        assert closer
        yield server, f"{TABLE_PAGE_PREFIX}{table_id}", closer


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_old_link_of_a_closed_table_with_games_shows_the_standings_and_the_games_and_never_who_closed_it(
    open_person: Callable[..., Page],
    page_errors: list[str],
    closed_with_games: tuple[RunningServer, str, str],
    form_factor: dict[str, Any],
) -> None:
    server, path, closer = closed_with_games
    person = record_page_errors(open_person(username="anna", server=server, **form_factor), page_errors)

    person.goto(f"{server.base_url}{path}")

    expect(person.get_by_role("heading", name=text(SOURCE_LANGUAGE, "closed.seriesEnded"))).to_be_visible()
    expect(person.get_by_text(text(SOURCE_LANGUAGE, "table.seriesGames", count=len(GAME_SEATS)))).to_be_visible()
    ranks = person.locator(".rank")
    expect(ranks).to_have_count(len(SEAT_NAMES))
    for seat, name in enumerate(SEAT_NAMES, start=1):
        rank = ranks.filter(has_text=name)
        expect(rank.locator(".dot")).to_have_class(re.compile(rf"\bseat-{seat}\b"))
        expect(rank.locator(".ai-mark")).to_have_count(1 if name == AGENT_NAME else 0)
        expect(rank.locator("small")).to_have_count(0)
    expect(person.locator(".gamesbox .grow")).to_have_count(len(GAME_SEATS))
    expect(person.get_by_text(closer)).to_have_count(0)
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect_the_panel_inside_the_viewport(person)


def test_a_game_of_the_closed_link_opens_its_sheet(
    open_person: Callable[..., Page], page_errors: list[str], closed_with_games: tuple[RunningServer, str, str]
) -> None:
    server, path, _ = closed_with_games
    person = record_page_errors(open_person(username="anna", server=server, **PHONE), page_errors)
    person.goto(f"{server.base_url}{path}")

    person.locator(".gamesbox .grow").first.click()

    expect(person.get_by_role("group", name=text(SOURCE_LANGUAGE, "table.sheetTitle", number="3"))).to_be_visible()


def test_the_sheet_of_a_game_of_the_closed_link_closes_by_its_way_back_by_escape_and_by_a_tap_beside_it(
    open_person: Callable[..., Page], page_errors: list[str], closed_with_games: tuple[RunningServer, str, str]
) -> None:
    server, path, _ = closed_with_games
    person = record_page_errors(open_person(username="anna", server=server, **PHONE), page_errors)
    person.goto(f"{server.base_url}{path}")
    first_game = person.locator(".gamesbox .grow").first
    sheet = person.locator(GAME_LIST)

    first_game.click()
    person.get_by_role("button", name=SHEET_BACK).click()
    expect(sheet).not_to_be_visible()

    first_game.click()
    person.locator(f"{GAME_LIST} .game-sheet").click()
    expect(sheet).to_be_visible()
    person.mouse.click(*BESIDE_THE_PANEL)
    expect(sheet).not_to_be_visible()

    first_game.click()
    person.keyboard.press("Escape")
    expect(sheet).not_to_be_visible()
    assert page_errors == []


def test_a_list_of_the_closed_link_the_server_cannot_read_says_so(
    open_person: Callable[..., Page], page_errors: list[str], closed_with_games: tuple[RunningServer, str, str]
) -> None:
    server, path, _ = closed_with_games
    # The browser logs the refused read as a console error; that refusal is the point of this test.
    person = record_page_errors(open_person(username="anna", server=server, **PHONE), page_errors, console=False)
    person.route(
        f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}",
        lambda route: route.fulfill(status=HTTPStatus.CONFLICT, content_type="application/json", body="{}"),
    )

    person.goto(f"{server.base_url}{path}")

    expect(person.locator(".gamesbox [role=alert]")).to_have_text(text(SOURCE_LANGUAGE, "table.seriesListFailed"))
    expect(person.locator(".gamesbox .grow")).to_have_count(0)
    assert page_errors == []


def test_a_new_table_opens_from_the_closed_link_with_games(
    open_person: Callable[..., Page], page_errors: list[str], closed_with_games: tuple[RunningServer, str, str]
) -> None:
    server, path, _ = closed_with_games
    person = record_page_errors(open_person(username="anna", server=server, **PHONE), page_errors)
    person.goto(f"{server.base_url}{path}")
    expect(person.locator(".gamesbox .grow")).to_have_count(len(GAME_SEATS))

    click_new_table(person)

    expect(person.get_by_text(text(SOURCE_LANGUAGE, "table.waitingForPlayers"))).to_be_visible()
    assert urlsplit(person.url).path != path
    assert page_errors == []
