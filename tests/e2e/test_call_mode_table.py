from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.call_frame import (
    CALL_FRAME_ATTRIBUTES,
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

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from playwright.sync_api import FrameLocator, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

UNKNOWN_ID = "0" * 32
BAR = ".bar"
WORDMARK = ".bar .wordmark"
APP_NAME = text(SOURCE_LANGUAGE, "app.name")
COPY_LINK = text(SOURCE_LANGUAGE, "table.copyLink")
NEW_TABLE = text(SOURCE_LANGUAGE, "start.newTable")
LOBBY = text(SOURCE_LANGUAGE, "table.lobby")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
SOUND_ON_NAME = text(SOURCE_LANGUAGE, "sound.panelName")
SOUND_OFF_NAME = text(SOURCE_LANGUAGE, "sound.muted")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
SPEAKER = ".actions .sound-button"


@pytest.fixture(scope="module")
def framing_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("call-mode"), call_origin=CALL_ORIGIN)


def page_filling_the_screen(address: str) -> str:
    """A call page whose frame is as large as the device's screen, as the call's own page gives its frame."""
    return (
        '<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><title>call</title>'
        f'<iframe id="stage" src="{address}" style="position:fixed;inset:0;width:100%;height:100%;border:0" '
        f"{CALL_FRAME_ATTRIBUTES}></iframe>"
    )


@contextmanager
def in_the_call_frame(
    visitor: Page, browser_coverage: BrowserCoverage, address: str, *, filling_the_screen: bool = False
) -> Generator[FrameLocator]:
    page = page_filling_the_screen(address) if filling_the_screen else page_holding(address)
    with served_from(CALL_ORIGIN, visitor, browser_coverage, page):
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
        expect(table.get_by_role("heading", name=text(SOURCE_LANGUAGE, "closed.notFound"))).to_be_visible()
        expect(table.get_by_role("button", name=NEW_TABLE)).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_top_level_call_mode_address_of_a_missing_table_offers_a_new_table(
    open_person: Callable[..., Page], framing_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    visitor = record_page_errors(open_person(server=framing_server, **form_factor), page_errors, console=False)

    visitor.goto(table_url(framing_server, f"{TABLE_PAGE_PREFIX}{UNKNOWN_ID}"))

    expect(visitor.get_by_role("heading", name=text(SOURCE_LANGUAGE, "closed.notFound"))).to_be_visible()
    expect(visitor.get_by_role("button", name=NEW_TABLE)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_table_holds_the_speaker_in_its_strip_beside_the_stand_up_button_and_opens_the_panel_above_it(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    path = new_table(open_person, framing_server)
    visitor = record_page_errors(open_person(server=framing_server, **form_factor), page_errors)
    viewport = visitor.viewport_size
    assert viewport is not None

    with in_the_call_frame(
        visitor, browser_coverage, table_url(framing_server, path), filling_the_screen=True
    ) as table:
        table.locator(f"{CHAIR}[data-seat='2']").get_by_role("button", name=SIT_DOWN).click()
        speaker = table.locator(SPEAKER)
        expect(speaker).to_be_visible()

        expect(table.locator(f"{BAR} .sound-button")).to_have_count(0)
        stand_up = table.get_by_role("button", name=STAND_UP).bounding_box()
        beside = speaker.bounding_box()
        assert stand_up is not None
        assert beside is not None
        assert beside["x"] >= stand_up["x"] + stand_up["width"]
        assert (
            table.locator(".actions > :not([popover])").evaluate_all(
                "tags => new Set(tags.map(tag => tag.offsetTop)).size"
            )
            == 1
        )

        face = speaker.locator(".sound-face")
        glass = face.evaluate("face => getComputedStyle(face).backgroundColor")
        speaker.click()
        expect(speaker).to_have_attribute("aria-expanded", "true")
        open_face = face.evaluate("face => [getComputedStyle(face).backgroundColor, getComputedStyle(face).color]")
        assert open_face[0] != glass
        assert open_face[0].startswith("rgb(")
        assert open_face[0] != open_face[1]
        panel = table.get_by_role("dialog", name=SOUND_ON_NAME).bounding_box()
        assert panel is not None
        assert panel["y"] >= 0
        assert panel["y"] + panel["height"] <= beside["y"]
        assert panel["x"] >= 0
        assert panel["x"] + panel["width"] <= viewport["width"]
    assert page_errors == []


def test_a_choice_made_in_a_call_holds_after_a_reload(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
) -> None:
    path = new_table(open_person, framing_server)
    visitor = record_page_errors(open_person(server=framing_server), page_errors)

    with in_the_call_frame(
        visitor, browser_coverage, table_url(framing_server, path), filling_the_screen=True
    ) as table:
        table.locator(SPEAKER).click()
        table.get_by_role("switch", name=TONE).set_checked(False)
        visitor.keyboard.press("Escape")
        expect(table.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()

        visitor.reload()

        expect(table.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()
    assert page_errors == []
