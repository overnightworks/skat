import json
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.audio import VOICES_OF_ONE_CARD, playing_table, tap, voices_started

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SETTINGS_KEY = "skat.settings"
# The default sound set's „Du bist dran“ is two tones.
VOICES_OF_THE_TURN = 2
BUZZ = [40]
RECORD_BUZZES = "window.buzzes = []; navigator.vibrate = (pattern) => { window.buzzes.push(pattern); return true; };"


@pytest.fixture
def table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> PlayingTable:
    return playing_table(open_person, e2e_server, member_of, page_errors)


def second_to_play(table: PlayingTable) -> Page:
    """The page of the seat that is on turn after the forehand's card."""
    return table.pages[table.seat_at["middlehand"]]


def keep_settings_and_reload(page: Page, settings: dict[str, object]) -> None:
    page.evaluate("([key, value]) => localStorage.setItem(key, value)", [SETTINGS_KEY, json.dumps(settings)])
    page.add_init_script(RECORD_BUZZES)
    page.reload()
    expect(page.locator(".chair")).to_have_count(3)


def hide_the_tab(page: Page) -> None:
    page.evaluate(
        """() => {
            Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
            document.dispatchEvent(new Event("visibilitychange"));
        }"""
    )


def test_the_turn_sounds_once_when_the_table_shows_it_and_not_again_for_the_moves_after_it(table: PlayingTable) -> None:
    second = second_to_play(table)
    tap(second)
    second.wait_for_timeout(500)
    before = len(voices_started(second))

    table.play_through_the_api(table.own_cards(table.seat_at["forehand"])[0])

    expect(second.locator(".chair.mine.turn")).to_be_visible()
    second.wait_for_function("count => window.voicesStarted.length >= count", arg=before + VOICES_OF_THE_TURN)
    # The card another seat laid sounds beside the turn.
    assert sorted(voice["kind"] for voice in voices_started(second)[before:]) == ["noise", "tone", "tone", "tone"]

    after_the_turn = len(voices_started(second))
    table.play_through_the_api(table.own_cards(table.seat_at["middlehand"])[0])
    expect(second.locator(".chair.mine.turn")).to_have_count(0)
    second.wait_for_function("count => window.voicesStarted.length >= count", arg=after_the_turn + VOICES_OF_ONE_CARD)
    # Only the player's own card sounds now; the turn has gone on to the next seat.
    assert len(voices_started(second)) == after_the_turn + VOICES_OF_ONE_CARD


def test_a_page_opened_on_the_turn_does_not_sound_it(table: PlayingTable) -> None:
    second = second_to_play(table)
    table.play_through_the_api(table.own_cards(table.seat_at["forehand"])[0])
    expect(second.locator(".chair.mine.turn")).to_be_visible()

    second.reload()
    expect(second.locator(".chair.mine.turn")).to_be_visible()
    tap(second)

    assert voices_started(second) == []


@pytest.mark.parametrize(("in_background", "voices"), [(False, 0), (True, VOICES_OF_THE_TURN)])
def test_a_hidden_tab_hears_the_turn_only_when_the_player_asked_for_it(
    table: PlayingTable, in_background: bool, voices: int
) -> None:
    second = second_to_play(table)
    keep_settings_and_reload(second, {"turnInBackground": in_background})
    tap(second)
    hide_the_tab(second)

    table.play_through_the_api(table.own_cards(table.seat_at["forehand"])[0])

    # A hidden window hears the turn alone: the card another seat laid is not wanted there.
    expect(second.locator(".chair.mine.turn")).to_be_visible()
    if voices:
        second.wait_for_function("count => window.voicesStarted.length >= count", arg=voices)
    else:
        second.wait_for_timeout(500)
    assert len(voices_started(second)) == voices


@pytest.mark.parametrize(("vibration", "buzzes"), [(False, []), (True, [BUZZ])])
def test_the_turn_vibrates_only_when_the_player_switched_it_on(
    table: PlayingTable, vibration: bool, buzzes: list[list[int]]
) -> None:
    second = second_to_play(table)
    keep_settings_and_reload(second, {"vibration": vibration})

    table.play_through_the_api(table.own_cards(table.seat_at["forehand"])[0])

    expect(second.locator(".chair.mine.turn")).to_be_visible()
    second.wait_for_timeout(500)
    assert second.evaluate("window.buzzes") == buzzes
