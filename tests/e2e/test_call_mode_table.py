import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.call import CALL_ORIGIN_PATH
from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.call_frame import (
    CALL_FRAME_ATTRIBUTES,
    CALL_ORIGIN,
    CHAIR,
    FRAME,
    HOPIN_FRAME_SIZES,
    THREE_CHAIRS,
    frame_of_size,
    greeting_page_holding,
    new_table,
    page_holding,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, WIDTHS
from tests.e2e.support.table_menu import AGENTS, MENU, menu_button, open_table_menu
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from playwright.sync_api import FrameLocator, Locator, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

UNKNOWN_ID = "0" * 32
APP_NAME = text(SOURCE_LANGUAGE, "app.name")
COPY_LINK = text(SOURCE_LANGUAGE, "table.copyLink")
NEW_TABLE = text(SOURCE_LANGUAGE, "start.newTable")
LOBBY = text(SOURCE_LANGUAGE, "table.lobby")
CALL = text(SOURCE_LANGUAGE, "table.call")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SOUND_ON_NAME = text(SOURCE_LANGUAGE, "sound.panelName")
SOUND_OFF_NAME = text(SOURCE_LANGUAGE, "sound.muted")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
CARDS_IN_A_TRICK = 3
LAST_TRICK = text(SOURCE_LANGUAGE, "play.lastTrick")
MORE = text(SOURCE_LANGUAGE, "table.menu")
REACTION_KEY = text(SOURCE_LANGUAGE, "table.reactions")
REACTION_TRAY = text(SOURCE_LANGUAGE, "table.reactionTray")
RULES = text(SOURCE_LANGUAGE, "rules.title")
RULES_CLOSE = text(SOURCE_LANGUAGE, "rules.close")
SERIES_LIST = text(SOURCE_LANGUAGE, "table.seriesList")
GAME_COUNT = re.compile(
    re.escape(text(SOURCE_LANGUAGE, "table.seriesCount", game="GAME", count="COUNT"))
    .replace("GAME", r"\d+")
    .replace("COUNT", r"\d+")
)
# What a person sees of the own hand lies inside the frame, and the frame has no scroll to reach the rest.
INSIDE_THE_FRAME = """(_, selector) => [...document.querySelectorAll(selector)].every((element) => {
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.top >= 0 && box.right <= innerWidth && box.bottom <= innerHeight;
})"""
SCROLLS = (
    "() => document.documentElement.scrollHeight > innerHeight || document.documentElement.scrollWidth > innerWidth"
)
OWN_HAND = ".own-hand"


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
def in_the_frame_of(visitor: Page, browser_coverage: BrowserCoverage, page: str) -> Generator[FrameLocator]:
    with served_from(CALL_ORIGIN, visitor, browser_coverage, page):
        # A page that already ran the app has its first navigation away cancelled and re-issued by the coverage
        # collector, which aborts a `goto`; the assignment leaves the page to follow the re-issue.
        visitor.evaluate("url => location.assign(url)", f"{CALL_ORIGIN}/")
        yield visitor.frame_locator(FRAME)


@contextmanager
def in_the_call_frame(
    visitor: Page, browser_coverage: BrowserCoverage, address: str, *, filling_the_screen: bool = False
) -> Generator[FrameLocator]:
    page = page_filling_the_screen(address) if filling_the_screen else page_holding(address)
    with in_the_frame_of(visitor, browser_coverage, page) as frame:
        yield frame


def speaker(table: Page | FrameLocator) -> Locator:
    return table.get_by_role("button", name=SOUND_ON_NAME, exact=True)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_call_mode_table_shows_its_wordmark_as_text_and_offers_a_seated_player_no_copy_link(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    with in_the_call_frame(visitor, browser_coverage, table_url(framing_server, path)) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)

        bar = table.get_by_role("banner")
        expect(bar.get_by_text(APP_NAME, exact=True)).to_be_visible()
        expect(bar.get_by_role("link")).to_have_count(0)
        sit_in(table, 2)
        expect(menu_button(table, STAND_UP)).to_be_visible()
        expect(menu_button(table, COPY_LINK)).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_call_mode_table_offers_its_opener_the_speaker(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    opener = open_person(server=framing_server, **form_factor)
    path = open_new_table(opener, framing_server)

    with in_the_call_frame(opener, browser_coverage, table_url(framing_server, path)) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)

        expect(speaker(table)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_top_level_call_mode_table_offers_the_lobby_button_and_its_copy_link(
    open_person: Callable[..., Page], framing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    visitor.goto(table_url(framing_server, path))

    expect(visitor.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    expect(visitor.get_by_role("link", name=LOBBY)).to_be_visible()
    expect(menu_button(visitor, COPY_LINK)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_anruf_key_opens_the_call_apps_start_link_for_the_table_in_a_new_tab_when_the_origin_is_set(
    open_person: Callable[..., Page], framing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    visitor.goto(f"{framing_server.base_url}{path}")
    sit_in(visitor, 2)

    key = visitor.get_by_role("link", name=CALL)
    expect(key).to_be_visible()
    expect(key).to_have_attribute("href", f"{CALL_ORIGIN}/c/new?app=skat&context={table_id_of(path)}")
    expect(key).to_have_attribute("target", "_blank")
    expect(key).to_have_attribute("rel", "noopener")


def watch_once_the_call_origin_is_read(visitor: Page, address: str) -> None:
    with visitor.expect_response(lambda response: response.url.endswith(CALL_ORIGIN_PATH)) as read:
        visitor.goto(address)
    read.value.finished()
    visitor.evaluate("() => new Promise((done) => requestAnimationFrame(() => done(null)))")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_watcher_has_no_anruf_key(
    open_person: Callable[..., Page], framing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    watch_once_the_call_origin_is_read(visitor, f"{framing_server.base_url}{path}")

    expect(visitor.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    expect(visitor.get_by_role("link", name=CALL)).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_anruf_key_is_absent_when_no_call_origin_is_set(
    open_person: Callable[..., Page], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    path = new_table(open_person, e2e_server)
    visitor = open_person(server=e2e_server, **form_factor)

    watch_once_the_call_origin_is_read(visitor, f"{e2e_server.base_url}{path}")

    expect(visitor.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    expect(visitor.get_by_role("link", name=CALL)).to_have_count(0)


def test_a_framed_call_mode_table_has_no_anruf_key(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)

    with in_the_call_frame(visitor, browser_coverage, table_url(framing_server, path)) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)

        expect(table.get_by_role("link", name=CALL)).to_have_count(0)


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
def test_a_framed_table_offers_a_seated_person_the_speaker_and_the_menu_and_opens_the_sound_panel_inside_the_frame(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    path = new_table(open_person, framing_server)
    visitor = record_page_errors(open_person(server=framing_server, **form_factor), page_errors)

    with in_the_call_frame(
        visitor, browser_coverage, table_url(framing_server, path), filling_the_screen=True
    ) as table:
        sit_in(table, 2)
        expect(speaker(table)).to_be_visible()

        expect(menu_button(table, STAND_UP)).to_be_visible()
        visitor.keyboard.press("Escape")
        expect(table.locator(MENU)).to_be_hidden()

        speaker(table).click()
        expect(speaker(table)).to_have_attribute("aria-expanded", "true")
        expect(table.get_by_role("dialog", name=SOUND_ON_NAME)).to_be_in_viewport(ratio=1)
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
        speaker(table).click()
        table.get_by_role("switch", name=TONE).set_checked(False)
        visitor.keyboard.press("Escape")
        expect(table.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()

        visitor.reload()

        expect(table.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()
    assert page_errors == []


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_result_in_a_call_offers_weiter_the_speaker_and_the_menu_key_inside_the_frame_and_the_menu_the_rest(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(
        open_person,
        framing_server,
        member_of,
        page_errors,
        {**form_factor, "server": framing_server, "groups": (AGENT_ADDERS_GROUP,)},
        console=False,
    )
    table.play_out(CARDS_IN_A_GAME)
    seated = table.pages[table.declarer_seat]
    path = f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}"

    with in_the_call_frame(seated, browser_coverage, table_url(framing_server, path), filling_the_screen=True) as call:
        for key in (call.get_by_role("button", name=WEITER), speaker(call), call.get_by_role("button", name=MORE)):
            expect(key).to_be_in_viewport(ratio=1)

        expect(menu_button(call, STAND_UP)).to_be_visible()
        expect(menu_button(call, AGENTS)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_on_the_winners_pile_of_a_framed_table_shows_the_last_trick(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(
        open_person,
        framing_server,
        member_of,
        page_errors,
        {**form_factor, "server": framing_server, "groups": (AGENT_ADDERS_GROUP,)},
        console=False,
    )
    table.play_out(CARDS_IN_A_TRICK)
    seated = table.pages[table.declarer_seat]
    path = f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}"

    with in_the_call_frame(seated, browser_coverage, table_url(framing_server, path), filling_the_screen=True) as call:
        call.get_by_role("button", name=LAST_TRICK).click()

        expect(call.get_by_role("dialog", name=LAST_TRICK).get_by_role("listitem")).to_have_count(CARDS_IN_A_TRICK)


@contextmanager
def in_a_hopin_frame(
    visitor: Page,
    table: PlayingTable,
    browser_coverage: BrowserCoverage,
    server: RunningServer,
    frame_size: tuple[int, int],
) -> Generator[FrameLocator]:
    """The table in a frame of the size hopin's stage gives it, before the call's greeting."""
    path = f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}"
    page = greeting_page_holding(table_url(server, path), server.base_url, frame_style=frame_of_size(*frame_size))
    with in_the_frame_of(visitor, browser_coverage, page) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        visitor.wait_for_function('window.messages.some((message) => message?.type === "ready")')
        yield table


def greet(visitor: Page, frame: FrameLocator) -> None:
    visitor.evaluate("greet()")
    expect(frame.get_by_role("banner")).to_have_count(0)


@pytest.fixture
def hopin_table(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    framing_server: RunningServer,
    page_errors: list[str],
    frame_size: tuple[int, int],
) -> PlayingTable:
    return deal_playing_table(
        open_person,
        framing_server,
        member_of,
        page_errors,
        {**device_of(frame_size), "server": framing_server},
        console=False,
    )


def device_of(frame_size: tuple[int, int]) -> dict[str, Any]:
    return DESKTOP if frame_size[0] > PHONE["viewport"]["width"] else PHONE


@pytest.mark.parametrize("frame_size", HOPIN_FRAME_SIZES.values(), ids=HOPIN_FRAME_SIZES)
def test_a_hopin_frame_holds_the_whole_table_the_own_hand_and_the_menu_key_before_and_after_the_greeting(
    hopin_table: PlayingTable,
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    frame_size: tuple[int, int],
) -> None:
    seated = hopin_table.pages[hopin_table.declarer_seat]

    with in_a_hopin_frame(seated, hopin_table, browser_coverage, framing_server, frame_size) as frame:
        expect(frame.locator(OWN_HAND)).to_be_visible()
        for greeted in (False, True):
            if greeted:
                greet(seated, frame)
            expect(frame.get_by_role("button", name=MORE)).to_be_in_viewport(ratio=1)
            for chair in frame.locator(CHAIR).all():
                expect(chair).to_be_in_viewport(ratio=1)

            assert frame.locator("body").evaluate(SCROLLS) is False
            assert frame.locator("body").evaluate(INSIDE_THE_FRAME, OWN_HAND) is True


@pytest.mark.parametrize("frame_size", HOPIN_FRAME_SIZES.values(), ids=HOPIN_FRAME_SIZES)
def test_the_reaction_key_works_in_a_hopin_frame_after_the_greeting(
    hopin_table: PlayingTable,
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    frame_size: tuple[int, int],
) -> None:
    seated = hopin_table.pages[hopin_table.declarer_seat]

    with in_a_hopin_frame(seated, hopin_table, browser_coverage, framing_server, frame_size) as frame:
        greet(seated, frame)
        tray = frame.get_by_role("group", name=REACTION_TRAY)
        key = frame.get_by_role("button", name=REACTION_KEY)
        if device_of(frame_size) is PHONE:
            expect(tray).to_be_hidden()
            key.click()
        else:
            expect(key).to_have_count(0)

        expect(tray).to_be_in_viewport(ratio=1)
        tray.get_by_role("button").first.click()
        if device_of(frame_size) is PHONE:
            expect(tray).to_be_hidden()


@pytest.mark.parametrize("frame_size", HOPIN_FRAME_SIZES.values(), ids=HOPIN_FRAME_SIZES)
def test_the_menu_in_a_hopin_frame_holds_the_game_count_only_after_the_greeting_and_always_the_rules(
    hopin_table: PlayingTable,
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    frame_size: tuple[int, int],
) -> None:
    seated = hopin_table.pages[hopin_table.declarer_seat]

    with in_a_hopin_frame(seated, hopin_table, browser_coverage, framing_server, frame_size) as frame:
        expect(menu_button(frame, RULES)).to_be_visible()
        expect(menu_button(frame, GAME_COUNT)).to_have_count(0)
        seated.keyboard.press("Escape")
        expect(frame.locator(MENU)).to_be_hidden()

        greet(seated, frame)
        open_table_menu(frame)

        expect(menu_button(frame, RULES)).to_be_visible()
        expect(frame.get_by_role("button", name=GAME_COUNT)).to_be_visible()
        expect(menu_button(frame, COPY_LINK)).to_have_count(0)
        menu_button(frame, RULES).click()
        expect(frame.get_by_role("dialog", name=RULES)).to_be_visible()
        frame.get_by_role("button", name=RULES_CLOSE).click()
        menu_button(frame, GAME_COUNT).click()
        expect(frame.get_by_role("dialog", name=SERIES_LIST)).to_be_visible()


@pytest.mark.parametrize("frame_size", HOPIN_FRAME_SIZES.values(), ids=HOPIN_FRAME_SIZES)
def test_a_watchers_menu_in_a_hopin_frame_holds_the_link_and_the_rules(
    hopin_table: PlayingTable,
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    frame_size: tuple[int, int],
) -> None:

    with in_a_hopin_frame(hopin_table.watcher, hopin_table, browser_coverage, framing_server, frame_size) as frame:
        greet(hopin_table.watcher, frame)
        open_table_menu(frame)

        expect(menu_button(frame, COPY_LINK)).to_be_visible()
        expect(menu_button(frame, RULES)).to_be_visible()
