"""The people at the table throw emotes from the tray and tap the objects of the table, and every page at the table,
a watcher's too, tells and plays each within a second; Klassik has an ambience of its own that sounds only after a tap.
"""

import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.table.records import TableStyle
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import RECORDING_COUNT, tap, voices_started, wait_for_recordings_decoded
from tests.e2e.support.people import DESKTOP, FORM_FACTORS
from tests.e2e.support.style import ROOM, give_the_table_its_style

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

pytestmark = pytest.mark.e2e

# A reaction reaches every page and is played within this many milliseconds of the throw.
SHOWN_WITHIN_MILLISECONDS = 1000
# The width from which the tray stands at the screen's edge as a rail and the key that opens it is gone.
RAIL_FROM_WIDTH = 900
TRAY_KEY = text(SOURCE_LANGUAGE, "table.reactions")
TRAY = text(SOURCE_LANGUAGE, "table.reactionTray")
CHEERS = text(SOURCE_LANGUAGE, "table.reactionCheers")
SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
# A coaster is a key named by its word and the total it shows.
COASTER = re.compile(rf"^{re.escape(text(SOURCE_LANGUAGE, 'table.objectCoaster'))} ")
EMOTES = [pytest.param("table.reactionFire", id="fire"), pytest.param("table.reactionKnock", id="knock")]
OBJECTS = [
    pytest.param(TableStyle.STRANDBAR, "table.objectCocktail", id="cocktail"),
    pytest.param(TableStyle.STRANDBAR, "table.objectShell", id="shell"),
    pytest.param(TableStyle.KLASSIK, "table.objectLamp", id="lamp"),
]
POLLING_MILLISECONDS = 100


def is_wide(person: Page) -> bool:
    viewport = person.viewport_size
    assert viewport is not None
    return viewport["width"] >= RAIL_FROM_WIDTH


def throwing_tray(person: Page) -> None:
    """The tray is open for a throw: a wide screen shows it always, a phone opens it from its key."""
    tray = person.get_by_role("group", name=TRAY)
    key = person.get_by_role("button", name=TRAY_KEY, exact=True)
    if is_wide(person):
        expect(key).to_be_hidden()
    else:
        expect(tray).to_be_hidden()
        key.click()
    expect(tray).to_be_visible()


def ready_to_hear(table: PlayingTable) -> dict[Page, int]:
    """A tap wakes the sound of every page; the voices each has started by now.

    The tap also fetches the voice's recordings, which a device that never chose the voice has on, so each page has
    decoded them before a reaction is timed against its second.
    """
    for person in table.everyone:
        tap(person)
    for person in table.everyone:
        wait_for_recordings_decoded(person, RECORDING_COUNT)
    return {person: len(voices_started(person)) for person in table.everyone}


def expect_played_by_every_page(heard_before: dict[Page, int]) -> None:
    for person, count in heard_before.items():
        person.wait_for_function(
            "count => window.voicesStarted.length > count",
            arg=count,
            timeout=SHOWN_WITHIN_MILLISECONDS,
            polling=POLLING_MILLISECONDS,
        )


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize("emote", EMOTES)
def test_an_emote_from_the_tray_is_told_with_its_throwers_name_on_every_page_and_sounds_within_a_second(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any], emote: str
) -> None:
    table = deal_a_game(form_factor)
    thrower_seat = table.seat_at["forehand"]
    thrower = table.pages[thrower_seat]
    heard_before = ready_to_hear(table)

    throwing_tray(thrower)
    thrower.get_by_role("button", name=text(SOURCE_LANGUAGE, emote)).click()

    told = f"{table.names[thrower_seat]} {text(SOURCE_LANGUAGE, emote)}"
    for person in table.everyone:
        expect(person.get_by_text(told, exact=True)).to_have_count(1, timeout=SHOWN_WITHIN_MILLISECONDS)
    expect_played_by_every_page(heard_before)
    if not is_wide(thrower):
        expect(thrower.get_by_role("group", name=TRAY)).to_be_hidden()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_watchers_emote_is_told_on_every_page_without_a_name(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game(form_factor)
    heard_before = ready_to_hear(table)

    throwing_tray(table.watcher)
    table.watcher.get_by_role("button", name=CHEERS).click()

    for person in table.everyone:
        expect(person.get_by_text(CHEERS, exact=True)).to_have_count(1, timeout=SHOWN_WITHIN_MILLISECONDS)
    expect_played_by_every_page(heard_before)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(("style", "object_word"), OBJECTS)
def test_a_tap_on_an_object_of_the_table_sounds_on_every_page(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any], style: TableStyle, object_word: str
) -> None:
    table = deal_a_game(form_factor)
    give_the_table_its_style(table.pages[table.seat_at["forehand"]], table.everyone, style)
    heard_before = ready_to_hear(table)

    table.watcher.get_by_role("button", name=text(SOURCE_LANGUAGE, object_word), exact=True).click()

    expect_played_by_every_page(heard_before)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_tap_on_a_coaster_sounds_on_every_page(
    deal_a_game: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game(form_factor)
    table.play_out(CARDS_IN_A_GAME)
    for person in table.everyone:
        expect(person.get_by_role("button", name=COASTER)).to_have_count(len(table.names))
    heard_before = ready_to_hear(table)

    table.watcher.get_by_role("button", name=COASTER).first.click()

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
