import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.table.asking import ASK_AGAIN_AFTER
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
    QUARTER_OVERLAP_JS,
    THREE_CHAIRS,
    chair_look,
    frame_of_size,
    greeting_page_holding,
    new_table,
    page_holding,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.declaring import AuctionCall, DeclaringTable, bids, passes
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, SMALL_PHONE, WIDTHS
from tests.e2e.support.table_menu import AGENTS, MENU, MENU_KEY, menu_button, open_table_menu
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from playwright.sync_api import FrameLocator, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

UNKNOWN_ID = "0" * 32
BAR = ".bar"
WORDMARK = ".bar .wordmark"
APP_NAME = text(SOURCE_LANGUAGE, "app.name")
COPY_LINK = text(SOURCE_LANGUAGE, "table.copyLink")
NEW_TABLE = text(SOURCE_LANGUAGE, "start.newTable")
LOBBY = text(SOURCE_LANGUAGE, "table.lobby")
CALL = text(SOURCE_LANGUAGE, "table.call")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
SOUND_ON_NAME = text(SOURCE_LANGUAGE, "sound.panelName")
SOUND_OFF_NAME = text(SOURCE_LANGUAGE, "sound.muted")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
SPEAKER = ".actions .sound-button"
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
CARDS_IN_A_TRICK = 3
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
# What a person sees of the table lies inside the frame, and the frame has no scroll to reach the rest.
INSIDE_THE_FRAME = """(_, selector) => [...document.querySelectorAll(selector)].every((element) => {
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.top >= 0 && box.right <= innerWidth && box.bottom <= innerHeight;
})"""
SCROLLS = (
    "() => document.documentElement.scrollHeight > innerHeight || document.documentElement.scrollWidth > innerWidth"
)
WHOLE_TABLE = f"{CHAIR}, .own-hand, .felt"


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

        expect(table.locator(WORDMARK)).to_have_text(APP_NAME)
        expect(table.locator(f"{BAR} a")).to_have_count(0)
        table.locator(f"{CHAIR}[data-seat='2']").get_by_role("button", name=SIT_DOWN).click()
        expect(menu_button(table, STAND_UP)).to_be_visible()
        expect(table.locator(".row.link")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_call_mode_table_offers_its_opener_the_speaker_and_no_close_key(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    opener = open_person(server=framing_server, **form_factor)
    path = open_new_table(opener, framing_server)

    with in_the_call_frame(opener, browser_coverage, table_url(framing_server, path)) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)

        expect(table.locator(SPEAKER)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_table_holds_its_rule_chips_in_the_top_row_beside_the_wordmark_and_the_watchers(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    path = open_new_table(open_person(server=framing_server), framing_server, running_points=True)
    visitor = open_person(server=framing_server, **form_factor)

    with in_the_call_frame(
        visitor, browser_coverage, table_url(framing_server, path), filling_the_screen=True
    ) as table:
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        wordmark = table.locator(WORDMARK).bounding_box()
        chips = table.locator(f"{BAR} .rulepill").bounding_box()
        watchers = table.locator(f"{BAR} .watchers").bounding_box()

        assert wordmark is not None
        assert chips is not None
        assert watchers is not None
        assert wordmark["y"] <= chips["y"] + chips["height"] / 2 <= wordmark["y"] + wordmark["height"]
        assert wordmark["x"] + wordmark["width"] <= chips["x"]
        assert chips["x"] + chips["width"] <= watchers["x"]


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

    key = visitor.locator(".actions").get_by_role("link", name=CALL)
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
def test_a_framed_table_holds_the_speaker_in_its_strip_beside_the_menu_key_and_opens_the_panel_above_it(
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
        menu_key = table.locator(f".actions {MENU_KEY}").bounding_box()
        beside = speaker.bounding_box()
        assert menu_key is not None
        assert beside is not None
        assert beside["x"] + beside["width"] <= menu_key["x"]
        assert (
            table.locator(".actions > :not([popover])").evaluate_all(
                "tags => new Set(tags.map(tag => tag.offsetTop)).size"
            )
            == 1
        )

        expect(menu_button(table, STAND_UP)).to_be_visible()
        visitor.keyboard.press("Escape")
        expect(table.locator(MENU)).to_be_hidden()

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


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_result_bar_in_a_call_holds_weiter_the_speaker_and_the_menu_key_in_one_row_and_the_menu_the_rest(
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
    viewport = seated.viewport_size
    assert viewport is not None
    path = f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}"

    with in_the_call_frame(seated, browser_coverage, table_url(framing_server, path), filling_the_screen=True) as call:
        bar = call.locator(".actions")
        expect(bar.get_by_role("button", name=WEITER)).to_be_visible()
        expect(bar.locator(".sound-button")).to_be_visible()
        expect(bar.locator(MENU_KEY)).to_be_visible()

        assert (
            bar.locator("> :not([popover])").evaluate_all("tags => new Set(tags.map(tag => tag.offsetTop)).size") == 1
        )
        last = bar.locator("> :not([popover])").last.bounding_box()
        assert last is not None
        assert last["x"] + last["width"] <= viewport["width"]

        expect(menu_button(call, STAND_UP)).to_be_visible()
        expect(menu_button(call, AGENTS)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_framed_table_lays_the_winners_pile_beside_its_chair_and_a_tap_on_it_shows_the_last_trick(
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
        pile = call.locator(".pile.last")
        expect(pile).to_be_visible()
        pile.click()

        expect(call.locator(".lastshow .lt-card")).to_have_count(CARDS_IN_A_TRICK)


class RearhandDeclaresTable(DeclaringTable):
    """The rearhand outbids the middlehand, so the declarer is the dealer and one chair carries both marks."""

    declarer_position = "rearhand"
    auction: ClassVar[tuple[AuctionCall, ...]] = (
        bids("middlehand", VALID_BIDS[0]),
        passes("forehand"),
        bids("rearhand", VALID_BIDS[1]),
        passes("middlehand"),
    )


@pytest.mark.parametrize("declaring", [DeclaringTable, RearhandDeclaresTable], ids=["one-mark", "dealer-declarer"])
@pytest.mark.parametrize("form_factor", [PHONE, DESKTOP], ids=["390", "1280"])
def test_a_framed_chair_keeps_its_marks_out_of_the_tiles_top_left_quarter_and_its_rims_outside_the_tile(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    declaring: type[DeclaringTable],
) -> None:
    table = deal_playing_table(
        open_person,
        framing_server,
        member_of,
        page_errors,
        {**form_factor, "server": framing_server},
        console=False,
        declaring=declaring,
    )
    seated = table.pages[table.declarer_seat]
    path = f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}"
    expect(seated.locator(CHAIR).locator(".mark:not(.pos)").first).to_be_visible()

    unframed = chair_look(seated)
    with in_the_call_frame(seated, browser_coverage, table_url(framing_server, path), filling_the_screen=True) as call:
        expect(call.locator(CHAIR).locator(".mark:not(.pos)").first).to_be_visible()
        framed = chair_look(call)

    assert framed["marks"] > 0
    assert framed["mostMarksOnAChair"] >= (2 if declaring is RearhandDeclaresTable else 1)
    assert framed["marksInTopLeftQuarter"] == 0
    assert framed["marksOverPositionLabel"] == 0
    assert framed["rimsInsideTile"] == 0
    assert framed["agentRimInsideTile"] == 0
    assert unframed["marks"] > 0
    assert framed["positionedMarks"] == 0
    assert unframed["positionedMarks"] > 0
    assert (unframed["barPillsShown"] > 0) == (form_factor is DESKTOP)
    assert unframed["rimsInsideTile"] > 0
    assert page_errors == []


# Every mark of a chair against its tile: how far it lies beyond the tile's edges, how many square pixels of it lie
# in the tile's top-left quarter, and how far its waiting dots reach beyond the mark itself.
_MARKS_AGAINST_THE_TILE_PROBE = """chair => {
    const quarterOverlap = QUARTER_OVERLAP;
    const tile = chair.querySelector(".tile").getBoundingClientRect();
    return [...chair.querySelectorAll(".mark:not(.pos)")].map(mark => {
        const box = mark.getBoundingClientRect();
        const dots = [...mark.querySelectorAll(".dots i")]
            .filter(dot => getComputedStyle(dot.parentElement).display !== "none");
        return {
            name: mark.className,
            outside: Math.max(
                tile.left - box.left, box.right - tile.right, tile.top - box.top, box.bottom - tile.bottom, 0),
            inQuarter: quarterOverlap(box, tile),
            dotsShown: dots.length,
            dotsOutside: Math.max(0, ...dots.map(dot => {
                const at = dot.getBoundingClientRect();
                return Math.max(box.left - at.left, at.right - box.right, box.top - at.top, at.bottom - box.bottom);
            })),
        };
    });
}""".replace("QUARTER_OVERLAP", QUARTER_OVERLAP_JS)


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", [SMALL_PHONE, PHONE], ids=["360", "390"])
@pytest.mark.parametrize("fourth_mark", ["bell", "away"])
def test_a_framed_chair_with_the_most_marks_a_chair_carries_keeps_them_inside_its_tile_and_out_of_the_top_left_quarter(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    fourth_mark: str,
) -> None:
    """The declaring dealer is on turn, so its chair carries the dealer, declarer and turn marks and one more: the bell
    the others may ring or, once its person left, the away mark; a chair that is away is not nudged, so never both."""
    table = RearhandDeclaresTable(
        open_person, framing_server, member_of, page_errors, {**form_factor, "server": framing_server}, console=False
    )
    watcher = table.others[0]
    if fourth_mark == "bell":
        watcher.clock.install()
    else:
        table.declarer.close()
    path = f"{TABLE_PAGE_PREFIX}{table.table_id}"

    with in_the_call_frame(watcher, browser_coverage, table_url(framing_server, path), filling_the_screen=True) as call:
        chair = call.locator(f"{CHAIR}[data-seat='{table.declarer_seat}']")
        if fourth_mark == "bell":
            expect(chair.locator(".mark.turn")).to_be_visible()
            watcher.clock.fast_forward("{:02d}:{:02d}".format(*divmod(int(ASK_AGAIN_AFTER), 60)))
        expect(chair.locator(f".mark.{fourth_mark}")).to_be_visible()
        marks = chair.evaluate(_MARKS_AGAINST_THE_TILE_PROBE)

    assert len(marks) == 4
    assert [mark for mark in marks if mark["outside"] > 0 or mark["inQuarter"] > 0] == []
    assert page_errors == []


@pytest.mark.parametrize("form_factor", [SMALL_PHONE, PHONE], ids=["360", "390"])
def test_a_framed_chair_with_three_marks_on_the_result_keeps_its_not_ready_mark_as_dots_inside_the_mark(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    """On the result screen a declarer who left and has not pressed Weiter carries declarer, not-ready and away."""
    table = deal_playing_table(
        open_person,
        framing_server,
        member_of,
        page_errors,
        {**form_factor, "server": framing_server},
        console=False,
    )
    table.play_out(CARDS_IN_A_GAME)
    table.pages[table.declarer_seat].close()
    seated = table.pages[next(seat for seat in table.pages if seat != table.declarer_seat)]
    path = f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}"

    with in_the_call_frame(seated, browser_coverage, table_url(framing_server, path), filling_the_screen=True) as call:
        chair = call.locator(f"{CHAIR}[data-seat='{table.declarer_seat}']")
        expect(chair.locator(".mark.away")).to_be_visible()
        expect(chair.locator(".mark.waits")).to_be_visible()
        marks = chair.evaluate(_MARKS_AGAINST_THE_TILE_PROBE)

    assert len(marks) == 3
    assert [mark for mark in marks if mark["outside"] > 0 or mark["inQuarter"] > 0] == []
    not_ready = next(mark for mark in marks if "waits" in mark["name"])
    assert not_ready["dotsShown"] == 3
    assert not_ready["dotsOutside"] == 0
    assert page_errors == []


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
    expect(frame.locator(BAR)).to_have_count(0)


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
        expect(frame.locator(".own-hand")).to_be_visible()
        for greeted in (False, True):
            if greeted:
                greet(seated, frame)
            expect(frame.get_by_role("button", name=MORE)).to_be_visible()

            assert frame.locator("body").evaluate(SCROLLS) is False
            assert frame.locator("body").evaluate(INSIDE_THE_FRAME, f"{WHOLE_TABLE}, .menu-key") is True


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

        expect(tray).to_be_visible()
        assert frame.locator("body").evaluate(INSIDE_THE_FRAME, ".tray") is True
        tray.get_by_role("button").first.click()
        if device_of(frame_size) is PHONE:
            expect(tray).to_be_hidden()


@pytest.mark.parametrize("frame_size", HOPIN_FRAME_SIZES.values(), ids=HOPIN_FRAME_SIZES)
def test_the_menu_in_a_hopin_frame_holds_the_rules_and_the_game_count_after_the_greeting(
    hopin_table: PlayingTable,
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    frame_size: tuple[int, int],
) -> None:
    seated = hopin_table.pages[hopin_table.declarer_seat]

    with in_a_hopin_frame(seated, hopin_table, browser_coverage, framing_server, frame_size) as frame:
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
