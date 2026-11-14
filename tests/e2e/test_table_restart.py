import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.constants import AUTH_START_PATH, GRACEFUL_SHUTDOWN_SECONDS
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE
from skat.web.words import text as word_text
from tests.e2e.support.browser import sign_in_at_issuer
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.sessions import holds_a_session

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from _pytest.logging import LogCaptureFixture

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

RECONNECTING = word_text(SOURCE_LANGUAGE, "table.reconnecting")
CARDS_PLAYED_BEFORE = 4
FACES = "(faces) => faces.map((face) => face.dataset.suit + face.dataset.rank).sort()"
FELT_CARD = ".trick .laid"
# What uvicorn logs when its graceful wait ends with a stream still running: a task cancelled, or its error.
STREAM_CANCELLED = re.compile(r"Cancel [1-9]\d* running task|CancelledError|Exception in ASGI application")
# The fan shows each card's left strip, and the next card covers its middle, where a plain click lands.
# The reloaded page signs in again and draws the table only after the answer; four workers' load stretches that.
BACK_AT_THE_TABLE_MILLISECONDS = 30_000
INSIDE_THE_VISIBLE_STRIP = {"x": 8, "y": 40}


@dataclass(frozen=True)
class View:
    """What a page shows of the table: every card face drawn and the plaque with the marks."""

    faces: list[str]
    plaque: str


@dataclass
class Restart:
    server_log: str
    views_before: dict[str, View]
    sign_in_starts: dict[str, list[str]]
    loads: dict[str, list[str]]
    dimmed_views: dict[str, View]


def view_of(page: Page) -> View:
    return View(page.locator(".card-face").evaluate_all(FACES), page.locator(".plaque").inner_text())


def restart_under_open_pages(table: PlayingTable, server: RunningServer, caplog: LogCaptureFixture) -> Restart:
    """Skat stops with every page open at the running hand and a new one starts; the sessions live in the database.

    Every page shows the table dimmed within the graceful wait of the stop, so the server ended its streams.
    """
    people = {table.names[seat]: page for seat, page in table.pages.items()} | {"dora": table.watcher}
    sign_in_starts: dict[str, list[str]] = {name: [] for name in people}
    loads: dict[str, list[str]] = {name: [] for name in people}
    for name, page in people.items():
        page.on(
            "request",
            lambda request, name=name: (
                sign_in_starts[name].append(request.url) if AUTH_START_PATH in request.url else None
            ),
        )
        page.on("load", lambda loaded, name=name: loads[name].append(loaded.url))
        sign_in_at_issuer(page, server, username=name)
        page.evaluate("window.sameDocument = true")
    views_before = {name: view_of(page) for name, page in people.items()}
    dimmed_views: dict[str, View] = {}

    def look_while_stopping() -> None:
        deadline = time.monotonic() + GRACEFUL_SHUTDOWN_SECONDS
        for name, page in people.items():
            remaining_milliseconds = max(1.0, (deadline - time.monotonic()) * 1000)
            expect(page.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible(
                timeout=remaining_milliseconds
            )
            expect(page.locator(".stage.stale")).to_have_count(1, timeout=remaining_milliseconds)
            dimmed_views[name] = view_of(page)

    uvicorn_log = logging.getLogger("uvicorn.error")
    uvicorn_log.addHandler(caplog.handler)
    try:
        server.restart(while_stopping=look_while_stopping)
    finally:
        uvicorn_log.removeHandler(caplog.handler)
    formatter = logging.Formatter()
    server_log = "\n".join(formatter.format(record) for record in caplog.records if record.name == "uvicorn.error")
    return Restart(server_log, views_before, sign_in_starts, loads, dimmed_views)


def expect_back_at_the_table(table: PlayingTable, restart: Restart, names: list[str]) -> None:
    pages = {table.names[seat]: page for seat, page in table.pages.items()} | {"dora": table.watcher}
    for name in names:
        page = pages[name]
        expect(page.locator(".chair")).to_have_count(3, timeout=BACK_AT_THE_TABLE_MILLISECONDS)
        expect(page.locator(".plaque")).to_have_text(
            restart.views_before[name].plaque, timeout=BACK_AT_THE_TABLE_MILLISECONDS
        )
        assert view_of(page) == restart.views_before[name]
        expect(page.locator(".stage.stale")).to_have_count(0)
        # The session outlived the restart, so the page stayed the same document and signed in nowhere.
        assert page.evaluate("window.sameDocument") is True
        assert restart.sign_in_starts[name] == []
        assert restart.loads[name] == []


@pytest.fixture
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """A Skat of its own for each test, so that restarting it leaves the shared server and its sign-ins alone."""
    with skat_on_new_database(tmp_path_factory) as server:
        yield server


@pytest.fixture
def playing_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    expected_request_failures: list[str],
) -> Callable[..., PlayingTable]:
    # The stopped server breaks the open streams and the session checks of the dimmed pages.
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")

    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, console=False)
        table.play_out(CARDS_PLAYED_BEFORE)
        for page in table.everyone:
            expect(page.locator(FELT_CARD)).to_have_count(1)
        return table

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_open_pages_come_back_signed_in_without_a_click_after_skat_restarts(
    playing_table: Callable[..., PlayingTable],
    e2e_server: RunningServer,
    caplog: LogCaptureFixture,
    form_factor: dict[str, Any],
) -> None:
    table = playing_table(form_factor)
    names = ["dora", *table.names.values()]

    restart = restart_under_open_pages(table, e2e_server, caplog)

    assert STREAM_CANCELLED.search(restart.server_log) is None
    assert restart.dimmed_views == restart.views_before
    expect_back_at_the_table(table, restart, names)
    assert all(holds_a_session(e2e_server, name) for name in names)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_after_the_restart_a_card_played_by_a_seated_member_reaches_every_page(
    playing_table: Callable[..., PlayingTable],
    e2e_server: RunningServer,
    caplog: LogCaptureFixture,
    form_factor: dict[str, Any],
) -> None:
    table = playing_table(form_factor)
    restart = restart_under_open_pages(table, e2e_server, caplog)
    expect_back_at_the_table(table, restart, ["dora", *table.names.values()])
    laid_before = table.watcher.locator(FELT_CARD).count()
    on_turn = int(table.watcher.locator(".chair.turn").get_attribute("data-seat") or "")

    table.pages[on_turn].locator(".own-hand .card.ok").first.dblclick(position=INSIDE_THE_VISIBLE_STRIP)

    for page in table.everyone:
        expect(page.locator(FELT_CARD)).to_have_count(laid_before + 1)
