from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.web.tables import TABLE_PAGE_PREFIX
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.call_frame import (
    CALL_ORIGIN,
    CHAIR,
    FRAME,
    THREE_CHAIRS,
    new_table,
    page_holding,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from playwright.sync_api import FrameLocator, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

UNKNOWN_ID = "0" * 32
BAR = ".bar"
WORDMARK = ".bar .wordmark"
APP_NAME = catalog_text("appName")
COPY_LINK = catalog_text("copyLink")
NEW_TABLE = catalog_text("newTable")
LOBBY = catalog_text("lobby")


@pytest.fixture(scope="module")
def framing_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("call-mode"), call_origin=CALL_ORIGIN)


@contextmanager
def in_the_call_frame(visitor: Page, browser_coverage: BrowserCoverage, address: str) -> Generator[FrameLocator]:
    with served_from(CALL_ORIGIN, visitor, browser_coverage, page_holding(address)):
        visitor.goto(f"{CALL_ORIGIN}/")
        yield visitor.frame_locator(FRAME)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_call_mode_table_shows_its_wordmark_as_text_and_offers_no_copy_link(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    with in_the_call_frame(visitor, browser_coverage, table_url(framing_server, path)) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)

        expect(table.locator(WORDMARK)).to_have_text(APP_NAME)
        expect(table.locator(f"{BAR} a")).to_have_count(0)
        expect(table.get_by_role("button", name=COPY_LINK)).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_top_level_call_mode_table_offers_the_lobby_button_and_its_copy_link(
    open_person: Callable[..., Page], framing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    visitor.goto(table_url(framing_server, path))

    expect(visitor.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    expect(visitor.get_by_role("link", name=LOBBY)).to_be_visible()
    expect(visitor.get_by_role("button", name=COPY_LINK)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_call_mode_address_of_a_missing_table_offers_no_new_table(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    visitor = record_page_errors(open_person(server=framing_server, **form_factor), page_errors, console=False)

    with in_the_call_frame(
        visitor, browser_coverage, table_url(framing_server, f"{TABLE_PAGE_PREFIX}{UNKNOWN_ID}")
    ) as table:
        expect(table.get_by_role("heading", name=catalog_text("tableNotFound"))).to_be_visible()
        expect(table.get_by_role("button", name=NEW_TABLE)).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_top_level_call_mode_address_of_a_missing_table_offers_a_new_table(
    open_person: Callable[..., Page], framing_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    visitor = record_page_errors(open_person(server=framing_server, **form_factor), page_errors, console=False)

    visitor.goto(table_url(framing_server, f"{TABLE_PAGE_PREFIX}{UNKNOWN_ID}"))

    expect(visitor.get_by_role("heading", name=catalog_text("tableNotFound"))).to_be_visible()
    expect(visitor.get_by_role("button", name=NEW_TABLE)).to_be_visible()
