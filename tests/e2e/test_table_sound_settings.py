import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.calling import TABLE_AGENTS_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import (
    FELT_FACE,
    VOICES_OF_ONE_CARD,
    open_at,
    open_watcher,
    playing_table,
    tap,
    voices_started,
)
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
VOLUME = text(SOURCE_LANGUAGE, "sound.volume")
SOUND_SETS = text(SOURCE_LANGUAGE, "sound.sets")
MOTION = text(SOURCE_LANGUAGE, "sound.motion")
REPLAY_MOTION = text(SOURCE_LANGUAGE, "sound.replayMotion")
REDUCED_NOTE = text(SOURCE_LANGUAGE, "sound.reducedMotionNote")
# The hand is a tilted fan whose cards cover each other, so a tap this far in from a card's left edge reaches it.
CARD_EDGE_INSET = 14
PLAYS_ONCE = text(SOURCE_LANGUAGE, "sound.playsOnce")
LEISE = text(SOURCE_LANGUAGE, "sound.setLeise")
STAMMTISCH = text(SOURCE_LANGUAGE, "sound.setStammtisch")
FUNKELN = text(SOURCE_LANGUAGE, "sound.setFunkeln")
DEZENT = text(SOURCE_LANGUAGE, "sound.motionDezent")
VERSPIELT = text(SOURCE_LANGUAGE, "sound.motionVerspielt")
LAST_TRICK = text(SOURCE_LANGUAGE, "sound.lastTrick")
SWEEP = text(SOURCE_LANGUAGE, "sound.lastTrickSweep")
STAY = text(SOURCE_LANGUAGE, "sound.lastTrickStay")
# The voices of a card in the sets "Stammtisch" and "Funkeln", in the order they start.
STAMMTISCH_KINDS = ["noise", "noise", "tone"]
FUNKELN_KINDS = ["tone", "noise", "tone"]
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


def uncovered_card_point(page: Page) -> tuple[float, float]:
    """A point on a card of the own hand, beside the open panel and outside of it."""
    panel = panel_of(page).bounding_box()
    assert panel is not None
    for card in page.locator(".own-hand .play").all():
        box = card.bounding_box()
        assert box is not None
        x, y = box["x"] + CARD_EDGE_INSET, box["y"] + box["height"] / 2
        if not (panel["x"] <= x <= panel["x"] + panel["width"] and panel["y"] <= y <= panel["y"] + panel["height"]):
            return x, y
    raise AssertionError("the open panel covers every card")


def test_the_tap_that_closes_the_panel_reaches_no_card(table: PlayingTable, page_errors: list[str]) -> None:
    forehand = table.pages[table.seat_at["forehand"]]
    open_the_panel(forehand)
    middle = uncovered_card_point(forehand)

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


def row_of(page: Page, name: str) -> Any:
    return panel_of(page).get_by_role("radiogroup", name=name)


def picked_in(page: Page, name: str) -> Any:
    """The name picked in a row of choices."""
    return row_of(page, name).get_by_role("radio", checked=True)


def volume_of(page: Page) -> Any:
    return panel_of(page).get_by_role("slider", name=VOLUME)


def pick(page: Page, row: str, name: str) -> None:
    row_of(page, row).get_by_role("radio", name=name).check()


def voice_kinds(page: Page) -> list[str]:
    return [voice["kind"] for voice in voices_started(page)]


def inside_the_viewport(page: Page) -> bool:
    return page.evaluate(
        """() => {
            const panel = document.querySelector('[role=dialog]').getBoundingClientRect();
            return panel.x >= 0 && panel.right <= innerWidth && panel.y >= 0 && panel.bottom <= innerHeight;
        }"""
    )


STORED = "localStorage.setItem({key!r}, {record!r})"


def stored_before_the_page_opens(page: Page, record: dict[str, Any]) -> None:
    page.add_init_script(STORED.format(key=SETTINGS_KEY, record=json.dumps(record)))


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize("device_motion", ["no-preference", "reduce"])
def test_the_panel_shows_the_volume_and_both_sets_at_their_defaults(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    device_motion: str,
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion=device_motion, **form_factor)

    open_the_panel(watcher)

    expect(volume_of(watcher)).to_have_value("70")
    expect(picked_in(watcher, SOUND_SETS)).to_have_accessible_name(LEISE)
    expect(picked_in(watcher, MOTION)).to_have_accessible_name(VERSPIELT)
    assert inside_the_viewport(watcher)
    assert not horizontal_scroll(watcher)
    assert page_errors == []


@pytest.mark.parametrize(
    ("device_motion", "asks_to_reduce"), [("no-preference", False), ("reduce", True)], ids=["moving", "reduced"]
)
def test_the_override_shows_only_where_the_device_asks_for_reduced_motion(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    device_motion: str,
    asks_to_reduce: bool,
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion=device_motion, **PHONE)

    open_the_panel(watcher)

    expect(panel_of(watcher).get_by_role("switch", name=REPLAY_MOTION)).to_have_count(int(asks_to_reduce))
    expect(panel_of(watcher).get_by_text(REDUCED_NOTE)).to_have_count(int(asks_to_reduce))
    expect(row_of(watcher, MOTION)).to_have_attribute("aria-disabled", str(asks_to_reduce).lower())
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_picked_last_trick_choice_is_stored_and_holds_after_a_reload(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion="no-preference", **form_factor)
    open_the_panel(watcher)
    expect(picked_in(watcher, LAST_TRICK)).to_have_accessible_name(SWEEP)

    pick(watcher, LAST_TRICK, STAY)

    expect(picked_in(watcher, LAST_TRICK)).to_have_accessible_name(STAY)
    assert json.loads(stored_record(watcher) or "") == {"lastTrick": "stay"}
    watcher.reload()
    expect(watcher.locator(".chair")).to_have_count(3)
    open_the_panel(watcher)

    expect(picked_in(watcher, LAST_TRICK)).to_have_accessible_name(STAY)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_picked_volume_and_picked_sets_hold_after_a_reload(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion="no-preference", **form_factor)
    open_the_panel(watcher)

    volume_of(watcher).focus()
    watcher.keyboard.press("End")
    pick(watcher, SOUND_SETS, FUNKELN)
    pick(watcher, MOTION, DEZENT)
    assert json.loads(stored_record(watcher) or "") == {"volume": 100, "soundSet": "funkeln", "motionSet": "dezent"}
    watcher.reload()
    expect(watcher.locator(".chair")).to_have_count(3)
    open_the_panel(watcher)

    expect(volume_of(watcher)).to_have_value("100")
    expect(panel_of(watcher).locator(".sound-value")).to_have_text("100")
    expect(picked_in(watcher, SOUND_SETS)).to_have_accessible_name(FUNKELN)
    expect(picked_in(watcher, MOTION)).to_have_accessible_name(DEZENT)
    assert page_errors == []


@pytest.mark.parametrize("sound_on", [True, False], ids=["sound-on", "sound-off"])
def test_picking_a_sound_set_sounds_its_card_once_and_says_so_only_while_the_sound_is_on(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], sound_on: bool
) -> None:
    watcher = open_at(open_person, page_errors, table, **PHONE)
    if not sound_on:
        switch_the_sound(watcher, on=False)
    open_the_panel(watcher)

    pick(watcher, SOUND_SETS, STAMMTISCH)

    expect(panel_of(watcher).get_by_text(PLAYS_ONCE)).to_have_count(int(sound_on))
    assert voice_kinds(watcher) == (STAMMTISCH_KINDS if sound_on else [])
    watcher.keyboard.press("Escape")
    open_the_panel(watcher)
    expect(panel_of(watcher).get_by_text(PLAYS_ONCE)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize(("soundset", "kinds"), [(STAMMTISCH, STAMMTISCH_KINDS), (FUNKELN, FUNKELN_KINDS)])
def test_a_played_card_sounds_in_the_picked_set(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], soundset: str, kinds: list[str]
) -> None:
    watcher = open_at(open_person, page_errors, table, **PHONE)
    open_the_panel(watcher)
    pick(watcher, SOUND_SETS, soundset)
    watcher.keyboard.press("Escape")
    preview = len(voices_started(watcher))

    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)

    assert voice_kinds(watcher)[preview:] == kinds
    assert page_errors == []


STORED_CHOICES = {"volume": 30, "soundSet": "stammtisch", "motionSet": "dezent", "replayMotion": True, "muted": True}
SHOWN_CHOICES = {"volume": "30", "sound": STAMMTISCH, "motion": DEZENT, "override": True, "tone": False}


def shown_choices(page: Page) -> dict[str, Any]:
    return {
        "volume": volume_of(page).input_value(),
        "sound": picked_in(page, SOUND_SETS).evaluate("node => node.parentElement.textContent.trim()"),
        "motion": picked_in(page, MOTION).evaluate("node => node.parentElement.textContent.trim()"),
        "override": panel_of(page).get_by_role("switch", name=REPLAY_MOTION).is_checked(),
        "tone": switch_of(page).is_checked(),
    }


@pytest.mark.parametrize(
    ("field", "bad", "shown", "default"),
    [
        ("volume", 500, "volume", "70"),
        ("volume", 12.5, "volume", "70"),
        ("soundSet", "laut", "sound", LEISE),
        ("motionSet", 7, "motion", VERSPIELT),
        ("replayMotion", "ja", "override", False),
        ("muted", 1, "tone", True),
    ],
)
def test_a_bad_stored_field_shows_its_default_and_leaves_the_other_fields_as_stored(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    field: str,
    bad: Any,
    shown: str,
    default: Any,
) -> None:
    watcher = record_page_errors(open_person(**PHONE), page_errors)
    stored_before_the_page_opens(watcher, {**STORED_CHOICES, field: bad})
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    open_the_panel(watcher)

    assert shown_choices(watcher) == {**SHOWN_CHOICES, shown: default}
    assert page_errors == []


def test_the_override_moves_a_card_in_the_chosen_set_and_the_device_setting_still_stills_it_without(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion="reduce", **PHONE)
    open_the_panel(watcher)
    expect(row_of(watcher, MOTION).get_by_role("radio", name=DEZENT)).to_be_disabled()

    panel_of(watcher).get_by_role("switch", name=REPLAY_MOTION).check()

    expect(row_of(watcher, MOTION).get_by_role("radio", name=DEZENT)).to_be_enabled()
    assert json.loads(stored_record(watcher) or "") == {"replayMotion": True}
    pick(watcher, MOTION, DEZENT)
    watcher.keyboard.press("Escape")
    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_css("animation-name", "land-dezent")
    assert page_errors == []


def test_a_panel_without_room_scrolls_and_says_there_is_more_until_its_end(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_at(open_person, page_errors, table, viewport={"width": 390, "height": 420}, is_mobile=True)
    open_the_panel(watcher)
    more = panel_of(watcher).locator(".sound-more")
    expect(more).to_be_visible()

    watcher.evaluate("document.querySelector('.sound-body').scrollTo(0, 10000)")

    expect(more).to_be_hidden()
    assert page_errors == []
