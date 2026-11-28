import json
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.audio import FELT_FACE, VOICES_OF_ONE_CARD, open_watcher, tap, voices_started
from tests.e2e.support.browser import hide_the_tab
from tests.e2e.support.declaring import reload_and_wait

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

pytestmark = pytest.mark.e2e

# The engine starts a voice a few hundredths of a second after the cue's time, so a card that sounds at once starts
# within a tenth of a second.
SOUNDS_WITHIN_SECONDS = 0.1
# The key the player's choice is kept under in the browser.
SETTINGS_KEY = "skat.settings"


def test_a_card_sounds_only_after_the_first_tap(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
) -> None:
    watcher = open_watcher(open_person, page_errors, table)

    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    assert voices_started(watcher) == []

    tap(watcher)
    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(2)

    assert {voice["kind"] for voice in voices_started(watcher)} == {"tone", "noise"}
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD
    assert page_errors == []


def test_a_card_played_before_the_page_opened_never_sounds(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
) -> None:
    table.play_out(1)
    joined = open_watcher(open_person, page_errors, table)
    expect(joined.locator(FELT_FACE)).to_have_count(1)

    tap(joined)
    assert voices_started(joined) == []

    joined.reload()
    expect(joined.locator(FELT_FACE)).to_have_count(1)
    tap(joined)
    assert voices_started(joined) == []

    table.play_out(1)
    expect(joined.locator(FELT_FACE)).to_have_count(2)
    assert len(voices_started(joined)) == VOICES_OF_ONE_CARD
    assert page_errors == []


def test_a_card_played_while_the_tab_is_hidden_never_sounds(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
) -> None:
    watcher = open_watcher(open_person, page_errors, table)
    tap(watcher)

    hide_the_tab(watcher, hidden=True)
    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    assert voices_started(watcher) == []

    hide_the_tab(watcher, hidden=False)
    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(2)
    assert len(voices_started(watcher)) == VOICES_OF_ONE_CARD
    assert page_errors == []


def test_the_viewers_own_card_sounds_louder_than_another_players(table: PlayingTable) -> None:
    own = table.pages[table.seat_at["forehand"]]
    tap(own)
    tap(table.watcher)

    table.play_out(1)
    expect(own.locator(FELT_FACE)).to_have_count(1)
    expect(table.watcher.locator(FELT_FACE)).to_have_count(1)

    own_level = max(voice["gain"] for voice in voices_started(own))
    watcher_level = max(voice["gain"] for voice in voices_started(table.watcher))
    assert 0 < watcher_level < own_level


def starts_of_one_card(page: Page) -> list[float]:
    starts = [voice["start"] for voice in voices_started(page)]
    assert len(starts) == VOICES_OF_ONE_CARD
    return starts


@pytest.mark.parametrize(
    ("device_motion", "stored"),
    [
        ("no-preference", {}),
        ("no-preference", {"motionSet": "dezent"}),
        ("reduce", {"motionSet": "dezent", "replayMotion": True}),
        ("reduce", {"replayMotion": True}),
    ],
    ids=["verspielt", "dezent", "reduced-but-overridden-dezent", "reduced-but-overridden"],
)
def test_a_still_card_sounds_at_once_and_a_card_that_moves_sounds_later(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    device_motion: str,
    stored: dict[str, object],
) -> None:
    still = open_watcher(open_person, page_errors, table)
    moving = open_watcher(open_person, page_errors, table, reduced_motion=device_motion)
    moving.evaluate("([key, record]) => localStorage.setItem(key, record)", [SETTINGS_KEY, json.dumps(stored)])
    reload_and_wait(moving)
    for watcher in (still, moving):
        tap(watcher)

    table.play_out(1)
    for watcher in (still, moving):
        expect(watcher.locator(FELT_FACE)).to_have_count(1)

    at_once = starts_of_one_card(still)
    assert all(0 < start < SOUNDS_WITHIN_SECONDS for start in at_once)
    assert min(starts_of_one_card(moving)) > max(at_once)
    assert page_errors == []
