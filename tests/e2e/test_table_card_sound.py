import json
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.audio import FELT_FACE, VOICES_OF_ONE_CARD, open_watcher, tap, voices_started
from tests.e2e.support.browser import hide_the_tab
from tests.e2e.support.motion import last_seconds_in_the_air, motion_played, watch_the_motion

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

pytestmark = pytest.mark.e2e

# A card sounds as it touches the felt: after the last frame that shows it in the air and, since the engine starts a
# voice a few hundredths of a second after the cue's time, within a tenth of a second of it.
SOUNDS_WITHIN_SECONDS = 0.1


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


@pytest.mark.parametrize(("motion", "moving"), [("reduce", False), ("no-preference", True)], ids=["still", "moving"])
def test_a_moving_card_sounds_when_it_lands_and_a_still_card_at_once(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    motion: str,
    moving: bool,
) -> None:
    watcher = open_watcher(open_person, page_errors, table, reduced_motion=motion)
    watch_the_motion(watcher)
    tap(watcher)

    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)

    starts = [voice["start"] for voice in voices_started(watcher)]
    assert len(starts) == VOICES_OF_ONE_CARD
    played = motion_played(watcher)
    assert bool(played) == moving
    in_the_air = last_seconds_in_the_air(played) if moving else 0
    assert all(in_the_air < start < in_the_air + SOUNDS_WITHIN_SECONDS for start in starts)
    assert page_errors == []


@pytest.mark.parametrize(
    ("device_motion", "stored"),
    [
        ("no-preference", {"motionSet": "dezent"}),
        ("reduce", {"motionSet": "dezent", "replayMotion": True}),
        ("reduce", {"replayMotion": True}),
    ],
    ids=["dezent", "reduced-but-overridden-dezent", "reduced-but-overridden"],
)
def test_a_card_sounds_when_it_lands_in_the_motion_set_the_table_moves_in(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    device_motion: str,
    stored: dict[str, object],
) -> None:
    watcher = open_watcher(open_person, page_errors, table, reduced_motion=device_motion)
    watcher.evaluate("record => localStorage.setItem('skat.settings', record)", json.dumps(stored))
    watcher.reload()
    expect(watcher.locator(".chair")).to_have_count(3)
    watch_the_motion(watcher)
    tap(watcher)

    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)

    starts = [voice["start"] for voice in voices_started(watcher)]
    in_the_air = last_seconds_in_the_air(motion_played(watcher))
    assert len(starts) == VOICES_OF_ONE_CARD
    assert all(in_the_air < start < in_the_air + SOUNDS_WITHIN_SECONDS for start in starts)
    assert page_errors == []
