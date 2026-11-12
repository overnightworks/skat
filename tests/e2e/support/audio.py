from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Page, expect

from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import PHONE

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

RECORDING_AUDIO_SCRIPT = Path(__file__).with_name("recording_audio.js")
FELT_FACE = ".trick .laid .face"
# One card sounds as one noise burst and one tone, and its voices start at the cue's time plus the engine's lead.
VOICES_OF_ONE_CARD = 2


def voices_started(page: Page) -> list[dict[str, Any]]:
    """The voices the page started on the recording stand-in for Web Audio, in the order they started."""
    return page.evaluate("window.voicesStarted")


def playing_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> PlayingTable:
    """Three people at a table in the play of a Kreuz game, a watcher beside them."""
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
