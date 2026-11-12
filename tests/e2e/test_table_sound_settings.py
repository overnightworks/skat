from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.calling import TABLE_AGENTS_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import FELT_FACE, VOICES_OF_ONE_CARD, open_watcher, playing_table, tap, voices_started
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.tables import open_new_table

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

# The key the player's choice is kept under in the browser; the privacy notice names it.
SETTINGS_KEY = "skat.settings"
SOUND_ON_NAME = text(SOURCE_LANGUAGE, "sound.panelName")
SOUND_OFF_NAME = text(SOURCE_LANGUAGE, "sound.muted")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
LOBBY = text(SOURCE_LANGUAGE, "table.lobby")
# A tap target is at least this many CSS pixels on each side.
TAP_TARGET_PIXELS = 44
# The desktop layout starts at this width, where the speaker carries its word.
DESKTOP_FROM_PIXELS = 900
# From this width the speaker stands left of the watchers; below it, right after the Lobby button.
LEFT_OF_WATCHERS_FROM_PIXELS = 390
# The pixels between the glass of the speaker and the glass of the button or pill beside it.
SPEAKER_GAP_PIXELS = 8
BROKEN_STORAGE = {
    "a record that is no JSON": f"localStorage.setItem({SETTINGS_KEY!r}, '{{muted')",
    "a read that throws": "Storage.prototype.getItem = () => { throw new Error('storage is blocked') }",
    "a write that throws": """{
        const set = Storage.prototype.setItem;
        Storage.prototype.setItem = function (...held) {
            if (this === window.localStorage) throw new DOMException('full', 'QuotaExceededError');
            return set.apply(this, held);
        };
    }""",
}


# The panel lies inside the viewport and over the middle of the speaker, below it.
PANEL_ON_ITS_BUTTON = """() => {
    const panel = document.querySelector('[role=dialog]').getBoundingClientRect();
    const speaker = document.querySelector('.sound-button').getBoundingClientRect();
    const middle = speaker.x + speaker.width / 2;
    return panel.x >= 0 && panel.right <= innerWidth && panel.x <= middle && middle <= panel.right
        && panel.y >= speaker.bottom;
}"""


# The tap targets are wider than the round glass inside them, so the gap is measured between the glass.
GLASS_GAP = """neighbour => {
    const speaker = document.querySelector('.sound-face').getBoundingClientRect();
    const watchers = document.querySelector('.watchers').getBoundingClientRect();
    const lobby = document.querySelector('.lobby-face').getBoundingClientRect();
    return neighbour === 'watchers' ? watchers.left - speaker.right : speaker.left - lobby.right;
}"""


@pytest.fixture
def table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> PlayingTable:
    return playing_table(open_person, e2e_server, member_of, page_errors)


def speaker_of(page: Page) -> Any:
    return page.locator(".sound-button")


def glass_gap(page: Page, neighbour: str) -> float:
    """The pixels between the speaker's glass and the glass of its neighbour in the top row."""
    return page.evaluate(GLASS_GAP, neighbour)


def panel_of(page: Page) -> Any:
    return page.get_by_role("dialog", name=SOUND_ON_NAME)


def switch_of(page: Page) -> Any:
    return page.get_by_role("switch", name=TONE)


def stored_record(page: Page) -> str | None:
    return page.evaluate("key => localStorage.getItem(key)", SETTINGS_KEY)


def open_the_panel(page: Page) -> None:
    speaker_of(page).click()
    expect(panel_of(page)).to_be_visible()


def switch_the_sound(page: Page, *, on: bool) -> None:
    open_the_panel(page)
    switch_of(page).set_checked(on)
    page.keyboard.press("Escape")
    expect(panel_of(page)).to_be_hidden()


def next_card(table: PlayingTable, watcher: Page, laid: int) -> None:
    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(laid)


def horizontal_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth > window.innerWidth")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_speaker_stands_clear_of_the_lobby_button_and_the_watchers(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(**form_factor), page_errors)
    open_new_table(person, e2e_server)

    expect(speaker_of(person)).to_be_visible()
    speaker = speaker_of(person).bounding_box()
    lobby = person.get_by_role("link", name=LOBBY).bounding_box()
    watchers = person.locator(".watchers").bounding_box()
    assert speaker is not None
    assert lobby is not None
    assert watchers is not None
    width = form_factor["viewport"]["width"]
    assert min(speaker["width"], speaker["height"]) >= TAP_TARGET_PIXELS
    assert lobby["x"] + lobby["width"] <= speaker["x"]
    assert speaker["x"] + speaker["width"] <= watchers["x"]
    assert (TONE in speaker_of(person).inner_text()) == (width >= DESKTOP_FROM_PIXELS)
    neighbour = "watchers" if width >= LEFT_OF_WATCHERS_FROM_PIXELS else "lobby"
    assert glass_gap(person, neighbour) == SPEAKER_GAP_PIXELS
    assert not horizontal_scroll(person)


def test_a_first_visit_stores_nothing(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_watcher(open_person, page_errors, table)
    assert stored_record(watcher) is None

    tap(watcher)
    assert stored_record(watcher) is None

    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    assert stored_record(watcher) is None
    assert page_errors == []


def test_muting_the_table_silences_the_next_card_and_turning_it_on_brings_the_sound_back(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_watcher(open_person, page_errors, table)

    switch_the_sound(watcher, on=False)
    assert stored_record(watcher) == '{"muted":true}'
    expect(watcher.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()
    expect(watcher.locator(".sound-button.muted")).to_have_count(1)
    next_card(table, watcher, 1)
    assert voices_started(watcher) == []

    switch_the_sound(watcher, on=True)
    assert stored_record(watcher) == '{"muted":false}'
    expect(watcher.get_by_role("button", name=SOUND_ON_NAME)).to_be_visible()
    expect(watcher.locator(".sound-button.muted")).to_have_count(0)
    next_card(table, watcher, 2)
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD
    assert page_errors == []


def test_a_reload_keeps_the_choice(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_watcher(open_person, page_errors, table)
    switch_the_sound(watcher, on=False)

    watcher.reload()

    expect(watcher.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()
    tap(watcher)
    next_card(table, watcher, 1)
    assert voices_started(watcher) == []
    assert page_errors == []


def test_the_tap_that_closes_the_panel_reaches_no_card(table: PlayingTable, page_errors: list[str]) -> None:
    forehand = table.pages[table.seat_at["forehand"]]
    card = forehand.locator(".own-hand .play").first
    box = card.bounding_box()
    assert box is not None
    middle = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    open_the_panel(forehand)
    forehand.mouse.click(*middle)

    expect(panel_of(forehand)).to_be_hidden()
    expect(forehand.locator(".own-hand .play[aria-pressed='true']")).to_have_count(0)
    forehand.mouse.click(*middle)
    expect(forehand.locator(".own-hand .play[aria-pressed='true']")).to_have_count(1)
    assert page_errors == []


def test_the_keyboard_opens_the_panel_switches_the_sound_and_leaves_with_escape(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_watcher(open_person, page_errors, table)
    speaker = speaker_of(watcher)
    speaker.focus()
    expect(speaker).to_have_attribute("aria-expanded", "false")

    watcher.keyboard.press("Enter")
    expect(speaker).to_have_attribute("aria-expanded", "true")
    expect(switch_of(watcher)).to_be_focused()
    watcher.keyboard.press("Space")
    assert stored_record(watcher) == '{"muted":true}'
    watcher.keyboard.press("Escape")

    expect(speaker).to_have_attribute("aria-expanded", "false")
    expect(speaker).to_be_focused()
    assert page_errors == []


def test_a_panel_opened_from_script_hands_the_focus_back_and_keeps_the_button_in_step(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_watcher(open_person, page_errors, table)
    speaker = speaker_of(watcher)

    watcher.evaluate("document.querySelector('[popover]').showPopover()")
    expect(speaker).to_have_attribute("aria-expanded", "true")
    watcher.evaluate("document.querySelector('[popover]').hidePopover()")

    expect(speaker).to_have_attribute("aria-expanded", "false")
    expect(speaker).to_be_focused()
    assert page_errors == []


def test_the_open_panel_follows_its_button_when_the_viewport_changes(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_watcher(open_person, page_errors, table)
    open_the_panel(watcher)

    for width in (360, 1280, 390):
        watcher.set_viewport_size({"width": width, "height": PHONE["viewport"]["height"]})

        watcher.wait_for_function(PANEL_ON_ITS_BUTTON)
    assert page_errors == []


def test_changing_the_setting_makes_no_request(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = record_page_errors(open_person(**PHONE), page_errors)
    # The page reads the agents once the stream brings its first table, which may come after the chairs show.
    with watcher.expect_request(lambda request: request.url.endswith(TABLE_AGENTS_SUFFIX)):
        watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    requested: list[str] = []
    watcher.on("request", lambda request: requested.append(request.url))

    open_the_panel(watcher)
    switch_of(watcher).set_checked(False)
    switch_of(watcher).set_checked(True)
    watcher.keyboard.press("Escape")

    expect(panel_of(watcher)).to_be_hidden()
    assert requested == []
    assert page_errors == []


@pytest.mark.parametrize("breakage", BROKEN_STORAGE)
def test_a_broken_storage_leaves_the_table_whole_and_the_switch_working(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], breakage: str
) -> None:
    watcher = record_page_errors(open_person(**PHONE), page_errors)
    watcher.add_init_script(BROKEN_STORAGE[breakage])
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    expect(watcher.get_by_role("button", name=SOUND_ON_NAME)).to_be_visible()
    tap(watcher)
    next_card(table, watcher, 1)
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD

    switch_the_sound(watcher, on=False)

    expect(watcher.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()
    next_card(table, watcher, 2)
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD
    assert page_errors == []


@pytest.mark.parametrize("motion", ["reduce", "no-preference"])
def test_the_panel_opens_at_once_whatever_the_device_asks_for_motion(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], motion: str
) -> None:
    watcher = open_watcher(open_person, page_errors, table, reduced_motion=motion)

    open_the_panel(watcher)

    moving = watcher.evaluate("document.getAnimations().filter(a => a.effect?.target?.closest?.('[popover]')).length")
    assert moving == 0
    assert page_errors == []
