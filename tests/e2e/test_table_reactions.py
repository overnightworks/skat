"""The people at the table throw emotes from the tray and tap the objects of the table, and every page at the table,
a watcher's too, shows and plays each within a second; Klassik has an ambience of its own that sounds only after a tap.
"""

import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.table.records import TableStyle
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import tap, voices_started
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, FORM_FACTORS, WIDTHS
from tests.e2e.support.style import ROOM, give_the_table_its_style

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

pytestmark = pytest.mark.e2e

# A reaction reaches every page and is played within this many milliseconds of the throw.
SHOWN_WITHIN_MILLISECONDS = 1000
# The width from which the tray stands at the screen's edge as a rail and the key that opens it is gone.
RAIL_FROM_WIDTH = 900
MINIMUM_TAP_AREA_PIXELS = 34
# Every test context asks for reduced motion; a motion under test needs the device to allow it.
MOTION_ALLOWED = {"reduced_motion": "no-preference"}
TRAY_KEY = text(SOURCE_LANGUAGE, "table.reactions")
TRAY = text(SOURCE_LANGUAGE, "table.reactionTray")
SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
EMOTE = ".thrown .emote"
KNOCK_RING = ".thrown .knock-ring"
KNOCK_RINGS_SPREAD = "knock-ring"
NO_ANIMATION = "none"
# The key the player's choices are kept under in the browser.
SETTINGS_KEY = "skat.settings"
TRAIL = ".thrown .emote-trail path"
COASTER = ".chair .coaster"
OBJECTS = [
    pytest.param(TableStyle.STRANDBAR, ".decor.cocktail", id="cocktail"),
    pytest.param(TableStyle.STRANDBAR, ".decor.shell", id="shell"),
    pytest.param(TableStyle.KLASSIK, ".decor.lamp", id="lamp"),
]
# Whether the element plays one of the two moves of an object of the table now.
MAKES_ITS_MOVE = """selector => document.querySelector(selector)?.getAnimations()
    .some(animation => animation.animationName.startsWith('object-beat')) === true"""
# The dotted trail of the flight is painted at some moment of it.
TRAIL_SHOWN = "() => Number(getComputedStyle(document.querySelector('.thrown .emote-trail')).opacity) > 0"
# Where the element's own place lies in the box of the layer that carries the emotes, before its motion moves it.
RESTING_PLACE = """selector => {
    const emote = document.querySelector(selector);
    const layer = emote.offsetParent;
    return {
        x: emote.offsetLeft + emote.offsetWidth / 2, y: emote.offsetTop + emote.offsetHeight / 2,
        width: layer.clientWidth, height: layer.clientHeight,
    };
}"""


# The place of the element in the layer that carries the emotes, before its motion moves it.
POSITION_IN_LAYER = "selector => { const e = document.querySelector(selector); return [e.offsetLeft, e.offsetTop]; }"
# Every key of the row of actions that stands on the screen, as its box.
ACTION_KEYS = """() => [...document.querySelectorAll('.actions button')]
    .map(key => key.getBoundingClientRect()).filter(box => box.width > 0)
    .map(box => ({ x: box.x, y: box.y, width: box.width, height: box.height }))"""


def is_wide(person: Page) -> bool:
    viewport = person.viewport_size
    assert viewport is not None
    return viewport["width"] >= RAIL_FROM_WIDTH


def throwing_tray(person: Page) -> None:
    """The tray is where the width puts it, open for a throw: a rail at the edge, or opened from its key."""
    tray = person.get_by_role("group", name=TRAY)
    key = person.get_by_role("button", name=TRAY_KEY, exact=True)
    if is_wide(person):
        expect(key).to_be_hidden()
    else:
        expect(tray).to_be_hidden()
        key.click()
    expect(tray).to_be_visible()
    viewport = person.viewport_size
    assert viewport is not None
    box = tray.bounding_box()
    assert box is not None
    if not is_wide(person):
        key_box = key.bounding_box()
        assert key_box is not None
        assert box["y"] >= key_box["y"] + key_box["height"]
    assert box["x"] >= 0
    assert box["x"] + box["width"] <= viewport["width"]
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= viewport["height"]


def ready_to_hear(table: PlayingTable) -> dict[Page, int]:
    """A tap wakes the sound of every page; the voices each has started by now."""
    for person in table.everyone:
        tap(person)
    return {person: len(voices_started(person)) for person in table.everyone}


def expect_played_by_every_page(heard_before: dict[Page, int]) -> None:
    for person, count in heard_before.items():
        person.wait_for_function(
            "count => window.voicesStarted.length > count", arg=count, timeout=SHOWN_WITHIN_MILLISECONDS
        )


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_an_emote_from_the_tray_flies_onto_the_felt_of_every_page_and_sounds_within_a_second(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game({**form_factor, **MOTION_ALLOWED})
    thrower_seat = table.seat_at["forehand"]
    thrower = table.pages[thrower_seat]
    heard_before = ready_to_hear(table)

    throwing_tray(thrower)
    thrower.get_by_role("button", name=text(SOURCE_LANGUAGE, "table.reactionFire")).click()

    for person in table.everyone:
        expect(person.locator(EMOTE)).to_have_count(1, timeout=SHOWN_WITHIN_MILLISECONDS)
        expect(person.locator(EMOTE)).to_contain_text(text(SOURCE_LANGUAGE, "table.reactionFireMark"))
        expect(person.locator(f"{EMOTE} .from")).to_have_text(table.names[thrower_seat][0])
        expect(person.locator(TRAIL)).to_have_count(1)
        place = person.evaluate(RESTING_PLACE, EMOTE)
        assert 0 <= place["x"] <= place["width"]
        assert 0 <= place["y"] <= place["height"]
    thrower.wait_for_function(TRAIL_SHOWN, timeout=SHOWN_WITHIN_MILLISECONDS * 2)
    expect_played_by_every_page(heard_before)
    if not is_wide(thrower):
        expect(thrower.get_by_role("group", name=TRAY)).to_be_hidden()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_open_tray_covers_no_key_of_the_row_of_actions(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game(form_factor)
    person = table.pages[table.seat_at["forehand"]]

    throwing_tray(person)

    tray = person.get_by_role("group", name=TRAY).bounding_box()
    assert tray is not None
    for key in person.evaluate(ACTION_KEYS):
        covers_across = tray["x"] < key["x"] + key["width"] and key["x"] < tray["x"] + tray["width"]
        covers_down = tray["y"] < key["y"] + key["height"] and key["y"] < tray["y"] + tray["height"]
        assert not (covers_across and covers_down)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(
    ("device_motion", "stored", "rings"),
    [
        (MOTION_ALLOWED["reduced_motion"], {"motionSet": "dezent"}, KNOCK_RINGS_SPREAD),
        (MOTION_ALLOWED["reduced_motion"], {"motionSet": "verspielt"}, KNOCK_RINGS_SPREAD),
        ("reduce", {"motionSet": "dezent"}, NO_ANIMATION),
    ],
    ids=["dezent", "verspielt", "reduced"],
)
def test_a_knock_lands_beside_its_chair_and_spreads_two_rings_as_the_motion_set_allows(
    deal_a_game: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    device_motion: str,
    stored: dict[str, Any],
    rings: str,
) -> None:
    table = deal_a_game({**form_factor, **MOTION_ALLOWED})
    observer = record_page_errors(open_person(reduced_motion=device_motion, **form_factor), page_errors)
    observer.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    observer.goto(table.watcher.url)
    expect(observer.locator(".chair")).to_have_count(len(table.names))

    thrower = table.pages[table.seat_at["forehand"]]
    throwing_tray(thrower)
    thrower.get_by_role("button", name=text(SOURCE_LANGUAGE, "table.reactionKnock")).click()

    expect(observer.locator(EMOTE)).to_contain_text(text(SOURCE_LANGUAGE, "table.reactionKnockMark"))
    expect(observer.locator(KNOCK_RING)).to_have_count(1)
    expect(observer.locator(KNOCK_RING)).to_have_css("animation-name", rings)
    expect(observer.locator(TRAIL)).to_have_count(0)
    assert observer.evaluate(POSITION_IN_LAYER, KNOCK_RING) == observer.evaluate(POSITION_IN_LAYER, EMOTE)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_watchers_emote_shows_on_every_page_without_a_name(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game({**form_factor, **MOTION_ALLOWED})
    heard_before = ready_to_hear(table)

    throwing_tray(table.watcher)
    table.watcher.get_by_role("button", name=text(SOURCE_LANGUAGE, "table.reactionCheers")).click()

    for person in table.everyone:
        expect(person.locator(EMOTE)).to_have_count(1, timeout=SHOWN_WITHIN_MILLISECONDS)
        expect(person.locator(EMOTE)).to_contain_text(text(SOURCE_LANGUAGE, "table.reactionCheersMark"))
        expect(person.locator(f"{EMOTE} .from")).to_have_count(0)
    expect_played_by_every_page(heard_before)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(("style", "object_selector"), OBJECTS)
def test_a_tap_on_an_object_of_the_table_makes_it_move_and_sound_on_every_page(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any], style: TableStyle, object_selector: str
) -> None:
    table = deal_a_game({**form_factor, **MOTION_ALLOWED})
    give_the_table_its_style(table.pages[table.seat_at["forehand"]], table.everyone, style)
    heard_before = ready_to_hear(table)
    for person in table.everyone:
        assert person.evaluate(MAKES_ITS_MOVE, object_selector) is False

    table.watcher.locator(object_selector).click()

    for person in table.everyone:
        person.wait_for_function(MAKES_ITS_MOVE, arg=object_selector, timeout=SHOWN_WITHIN_MILLISECONDS)
    expect_played_by_every_page(heard_before)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_tap_on_a_coaster_makes_every_coaster_move_and_sound_on_every_page(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game({**form_factor, **MOTION_ALLOWED})
    table.play_out(CARDS_IN_A_GAME)
    for person in table.everyone:
        expect(person.locator(COASTER)).to_have_count(len(table.names))
    heard_before = ready_to_hear(table)
    coaster = table.watcher.locator(COASTER).first
    assert min(coaster.evaluate("element => [element.offsetWidth, element.offsetHeight]")) >= MINIMUM_TAP_AREA_PIXELS

    coaster.click()

    for person in table.everyone:
        person.wait_for_function(MAKES_ITS_MOVE, arg=COASTER, timeout=SHOWN_WITHIN_MILLISECONDS)
    expect_played_by_every_page(heard_before)


def test_klassiks_ambience_starts_only_after_a_tap_and_follows_the_mute(
    deal_a_game: Callable[..., PlayingTable],
) -> None:
    table = deal_a_game(DESKTOP)
    watcher = table.watcher
    expect(watcher.locator(ROOM)).to_have_attribute("data-style", TableStyle.KLASSIK.value)
    assert watcher.evaluate("window.seaStarts") == 0

    tap(watcher)

    watcher.wait_for_function("window.seaStarts > 0")
    assert watcher.evaluate("window.seaLevels.at(-1)") > 0
    watcher.get_by_role("button", name=SOUND_PANEL).click()
    watcher.get_by_role("switch", name=TONE).set_checked(False)
    watcher.wait_for_function("window.seaLevels.at(-1) === 0")
