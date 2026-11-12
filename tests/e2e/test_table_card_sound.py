from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.audio import voices_started
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import PHONE

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

FELT_FACE = ".trick .laid .face"
# One card sounds as one noise burst and one tone, and its voices start at the cue's time plus the engine's lead.
VOICES_OF_ONE_CARD = 2
LANDING_SECONDS = 0.28


@pytest.fixture
def table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> PlayingTable:
    return deal_playing_table(open_person, e2e_server, member_of, page_errors, PHONE, game="kreuz")


def open_watcher(
    open_person: Callable[..., Page], page_errors: list[str], table: PlayingTable, **form_factor: object
) -> Page:
    watcher = record_page_errors(open_person(**PHONE, **form_factor), page_errors)
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    return watcher


def tap(page: Page) -> None:
    page.keyboard.press("Shift")


def hide_the_tab(page: Page, *, hidden: bool) -> None:
    page.evaluate(
        """hidden => {
            Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
            document.dispatchEvent(new Event("visibilitychange"));
        }""",
        hidden,
    )


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
    tap(watcher)

    table.play_out(1)
    expect(watcher.locator(FELT_FACE)).to_have_count(1)

    starts = [voice["start"] for voice in voices_started(watcher)]
    assert len(starts) == VOICES_OF_ONE_CARD
    assert all((start >= LANDING_SECONDS) == moving for start in starts)
    assert page_errors == []
