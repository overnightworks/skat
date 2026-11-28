import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.calling import TABLE_AGENTS_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.audio import (
    FELT_FACE,
    RECORDING_COUNT,
    VOICES_OF_ONE_CARD,
    open_at,
    open_watcher,
    tap,
    voices_started,
    wait_for_recordings_decoded,
)
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.declaring import reload_and_wait
from tests.e2e.support.people import PHONE, WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

pytestmark = pytest.mark.e2e

# The key the player's choice is kept under in the browser; the privacy notice names it.
SETTINGS_KEY = "skat.settings"
SOUND_ON_NAME = text(SOURCE_LANGUAGE, "sound.panelName")
SOUND_OFF_NAME = text(SOURCE_LANGUAGE, "sound.muted")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
VOLUME = text(SOURCE_LANGUAGE, "sound.volume")
SOUND_SETS = text(SOURCE_LANGUAGE, "sound.sets")
MOTION = text(SOURCE_LANGUAGE, "sound.motion")
REPLAY_MOTION = text(SOURCE_LANGUAGE, "sound.replayMotion")
VOICE = text(SOURCE_LANGUAGE, "sound.voice")
REDUCED_NOTE = text(SOURCE_LANGUAGE, "sound.reducedMotionNote")
MORE = text(SOURCE_LANGUAGE, "sound.more")
# The hand is a tilted fan whose cards cover each other, so a tap this far in from a card's left edge reaches it.
CARD_EDGE_INSET = 14
PLAYS_ONCE = text(SOURCE_LANGUAGE, "sound.playsOnce")
LEISE = text(SOURCE_LANGUAGE, "sound.setLeise")
STAMMTISCH = text(SOURCE_LANGUAGE, "sound.setStammtisch")
FUNKELN = text(SOURCE_LANGUAGE, "sound.setFunkeln")
DEZENT = text(SOURCE_LANGUAGE, "sound.motionDezent")
VERSPIELT = text(SOURCE_LANGUAGE, "sound.motionVerspielt")
LAST_TRICK = text(SOURCE_LANGUAGE, "sound.lastTrick")
TURN_IN_BACKGROUND = text(SOURCE_LANGUAGE, "sound.turnInBackground")
VIBRATION = text(SOURCE_LANGUAGE, "sound.vibration")
SWEEP = text(SOURCE_LANGUAGE, "sound.lastTrickSweep")
STAY = text(SOURCE_LANGUAGE, "sound.lastTrickStay")
# The voices of a card in the sets "Leise" and "Funkeln", in the order they start.
LEISE_KINDS = ["noise", "tone"]
FUNKELN_KINDS = ["tone", "noise", "tone"]
# A wheel turn longer than the panel's rows are high, which ends at the panel's end.
PAST_THE_PANELS_END_PIXELS = 10_000
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


def speaker_of(page: Page) -> Locator:
    """The key of the sound panel, whose name says whether the sound is off."""
    return page.get_by_role("button", name=SOUND_ON_NAME, exact=True).or_(
        page.get_by_role("button", name=SOUND_OFF_NAME, exact=True)
    )


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
    next_card(table, watcher, 1)
    assert voices_started(watcher) == []

    switch_the_sound(watcher, on=True)
    assert stored_record(watcher) == '{"muted":false}'
    expect(watcher.get_by_role("button", name=SOUND_ON_NAME)).to_be_visible()
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


def playable_cards(page: Page) -> Locator:
    return old_surface.own_cards(page).get_by_role("button")


def uncovered_card_point(page: Page) -> tuple[float, float]:
    """A point on a card of the own hand, beside the open panel and outside of it.

    The fan shows each card's left strip and the last card whole, so the points are the strips and the last card's
    right edge.
    """
    panel = panel_of(page).bounding_box()
    assert panel is not None
    boxes = [card.bounding_box() for card in playable_cards(page).all()]
    assert None not in boxes
    cards = [box for box in boxes if box]
    points = [(box["x"] + CARD_EDGE_INSET, box["y"] + box["height"] / 2) for box in cards]
    last = cards[-1]
    points.append((last["x"] + last["width"] - CARD_EDGE_INSET, last["y"] + last["height"] / 2))
    for x, y in points:
        if not (panel["x"] <= x <= panel["x"] + panel["width"] and panel["y"] <= y <= panel["y"] + panel["height"]):
            return x, y
    raise AssertionError("the open panel covers every card")


def test_the_tap_that_closes_the_panel_reaches_no_card(table: PlayingTable, page_errors: list[str]) -> None:
    forehand = table.pages[table.seat_at["forehand"]]
    open_the_panel(forehand)
    middle = uncovered_card_point(forehand)

    forehand.mouse.click(*middle)

    expect(panel_of(forehand)).to_be_hidden()
    expect(old_surface.own_cards(forehand).get_by_role("button", pressed=True)).to_have_count(0)
    forehand.mouse.click(*middle)
    expect(old_surface.own_cards(forehand).get_by_role("button", pressed=True)).to_have_count(1)
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


# Measured on today's panel: no other test resizes the viewport under an open panel.
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
    old_surface.expect_the_table_shown(watcher)
    # The first tap fetches the voice's recordings, which a device that never chose the voice has on.
    tap(watcher)
    wait_for_recordings_decoded(watcher, RECORDING_COUNT)
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
    old_surface.expect_the_table_shown(watcher)
    expect(watcher.get_by_role("button", name=SOUND_ON_NAME)).to_be_visible()
    tap(watcher)
    next_card(table, watcher, 1)
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD

    switch_the_sound(watcher, on=False)

    expect(watcher.get_by_role("button", name=SOUND_OFF_NAME)).to_be_visible()
    next_card(table, watcher, 2)
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD
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


STORED = "localStorage.setItem({key!r}, {record!r})"


def stored_before_the_page_opens(page: Page, record: dict[str, Any]) -> None:
    page.add_init_script(STORED.format(key=SETTINGS_KEY, record=json.dumps(record)))


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize("device_motion", ["no-preference", "reduce"])
def test_the_panel_shows_the_volume_both_sets_and_the_voice_at_their_defaults(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    device_motion: str,
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion=device_motion, **form_factor)

    open_the_panel(watcher)

    expect(volume_of(watcher)).to_have_value("70")
    expect(picked_in(watcher, SOUND_SETS)).to_have_accessible_name(STAMMTISCH)
    expect(picked_in(watcher, MOTION)).to_have_accessible_name(VERSPIELT)
    expect(panel_of(watcher).get_by_role("switch", name=VOICE)).to_be_checked()
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
    reload_and_wait(watcher)
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
    reload_and_wait(watcher)
    open_the_panel(watcher)

    expect(volume_of(watcher)).to_have_value("100")
    expect(panel_of(watcher).get_by_role("status")).to_have_text("100")
    expect(picked_in(watcher, SOUND_SETS)).to_have_accessible_name(FUNKELN)
    expect(picked_in(watcher, MOTION)).to_have_accessible_name(DEZENT)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_turn_cue_switches_are_stored_and_hold_after_a_reload(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion="no-preference", **form_factor)
    open_the_panel(watcher)
    for name in (TURN_IN_BACKGROUND, VIBRATION):
        expect(panel_of(watcher).get_by_role("switch", name=name)).not_to_be_checked()

    # The keyboard flips the focused switch wherever the rows sit; a pointer can meet a row that shifted.
    for name in (TURN_IN_BACKGROUND, VIBRATION):
        panel_of(watcher).get_by_role("switch", name=name).press("Space")

    assert json.loads(stored_record(watcher) or "") == {"turnInBackground": True, "vibration": True}
    reload_and_wait(watcher)
    open_the_panel(watcher)

    for name in (TURN_IN_BACKGROUND, VIBRATION):
        expect(panel_of(watcher).get_by_role("switch", name=name)).to_be_checked()
    assert page_errors == []


@pytest.mark.parametrize("sound_on", [True, False], ids=["sound-on", "sound-off"])
def test_picking_a_sound_set_sounds_its_card_once_and_says_so_only_while_the_sound_is_on(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], sound_on: bool
) -> None:
    watcher = open_at(open_person, page_errors, table, **PHONE)
    if not sound_on:
        switch_the_sound(watcher, on=False)
    open_the_panel(watcher)

    pick(watcher, SOUND_SETS, FUNKELN)

    expect(panel_of(watcher).get_by_text(PLAYS_ONCE)).to_have_count(int(sound_on))
    assert voice_kinds(watcher) == (FUNKELN_KINDS if sound_on else [])
    watcher.keyboard.press("Escape")
    open_the_panel(watcher)
    expect(panel_of(watcher).get_by_text(PLAYS_ONCE)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("sound_on", [True, False], ids=["sound-on", "sound-off"])
def test_releasing_the_volume_slider_sounds_one_card_while_the_sound_is_on(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str], sound_on: bool
) -> None:
    watcher = open_at(open_person, page_errors, table, **PHONE)
    if not sound_on:
        switch_the_sound(watcher, on=False)
    open_the_panel(watcher)

    volume_of(watcher).focus()
    watcher.keyboard.press("End")

    assert len(voices_started(watcher)) == (VOICES_OF_ONE_CARD if sound_on else 0)
    assert page_errors == []


@pytest.mark.parametrize(("soundset", "kinds"), [(LEISE, LEISE_KINDS), (FUNKELN, FUNKELN_KINDS)])
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


STORED_CHOICES = {"volume": 30, "soundSet": "funkeln", "motionSet": "dezent", "replayMotion": True, "muted": True}
SHOWN_CHOICES = {"volume": "30", "sound": FUNKELN, "motion": DEZENT, "override": True, "tone": False}


def expect_the_choices(page: Page, shown: dict[str, Any]) -> None:
    expect(volume_of(page)).to_have_value(shown["volume"])
    expect(picked_in(page, SOUND_SETS)).to_have_accessible_name(shown["sound"])
    expect(picked_in(page, MOTION)).to_have_accessible_name(shown["motion"])
    expect(panel_of(page).get_by_role("switch", name=REPLAY_MOTION)).to_be_checked(checked=shown["override"])
    expect(switch_of(page)).to_be_checked(checked=shown["tone"])


@pytest.mark.parametrize(
    ("field", "bad", "shown", "default"),
    [
        ("volume", 500, "volume", "70"),
        ("volume", 12.5, "volume", "70"),
        ("soundSet", "laut", "sound", STAMMTISCH),
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
    old_surface.expect_the_table_shown(watcher)
    open_the_panel(watcher)

    expect_the_choices(watcher, {**SHOWN_CHOICES, shown: default})
    assert page_errors == []


def test_the_override_lets_a_motion_set_be_picked_where_the_device_asks_for_reduced_motion(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_at(open_person, page_errors, table, reduced_motion="reduce", **PHONE)
    open_the_panel(watcher)
    expect(row_of(watcher, MOTION).get_by_role("radio", name=DEZENT)).to_be_disabled()

    panel_of(watcher).get_by_role("switch", name=REPLAY_MOTION).check()

    expect(row_of(watcher, MOTION).get_by_role("radio", name=DEZENT)).to_be_enabled()
    assert json.loads(stored_record(watcher) or "") == {"replayMotion": True}
    pick(watcher, MOTION, DEZENT)
    expect(picked_in(watcher, MOTION)).to_have_accessible_name(DEZENT)
    assert page_errors == []


def test_a_panel_without_room_scrolls_and_says_there_is_more_until_its_end(
    table: PlayingTable, open_person: Callable[..., Page], page_errors: list[str]
) -> None:
    watcher = open_at(open_person, page_errors, table, viewport={"width": 390, "height": 420}, is_mobile=True)
    open_the_panel(watcher)
    more = panel_of(watcher).get_by_text(MORE, exact=True)
    expect(more).to_be_visible()

    panel_of(watcher).hover()
    watcher.mouse.wheel(0, PAST_THE_PANELS_END_PIXELS)

    expect(more).to_be_hidden()
    assert page_errors == []
