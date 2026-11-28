import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skat.web.words import SOURCE_LANGUAGE, WORDS
from tests.e2e.support import old_surface
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import PHONE

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

RECORDING_AUDIO_SCRIPT = Path(__file__).with_name("recording_audio.js")
FELT_FACE = old_surface.FELT_FACE
# A card in the set a device starts with, „Stammtisch“, sounds as two noise bursts and one tone, and its voices start at
# the cue's time plus the engine's lead.
VOICES_OF_ONE_CARD = 3
# The recordings of the page's language, which the page decodes once its voice is on.
RECORDING_COUNT = sum(key.startswith("voice.") for key in WORDS[SOURCE_LANGUAGE])
# The file of a recording is named by its catalog key and a hash of its bytes, after a dot.
RECORDED_KEY = re.compile(r"/(voice\.\w+)\.[\w-]+\.mp3$")
# The confirmations the voice says for a hold instead of its number.
CONFIRMATIONS = {key for key in WORDS[SOURCE_LANGUAGE] if key.startswith("voice.hold")}


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


def open_at(open_person: Callable[..., Page], page_errors: list[str], table: PlayingTable, **context: Any) -> Page:
    """The table's watcher page, opened in the browser context the keywords describe."""
    watcher = record_page_errors(open_person(**context), page_errors)
    watcher.goto(table.watcher.url)
    old_surface.expect_the_table_shown(watcher)
    return watcher


def open_watcher(
    open_person: Callable[..., Page], page_errors: list[str], table: PlayingTable, **form_factor: object
) -> Page:
    return open_at(open_person, page_errors, table, **PHONE, **form_factor)


def tap(page: Page) -> None:
    page.keyboard.press("Shift")


def recordings_started(page: Page) -> list[dict[str, Any]]:
    """The recordings the page played on the stand-in in the order they started, with the path each came from."""
    return page.evaluate("window.recordingsStarted")


def keys_said(page: Page) -> list[str]:
    """The catalog keys of the recordings the page played, in the order they started."""
    found = [RECORDED_KEY.search(recording["url"]) for recording in recordings_started(page)]
    return [match.group(1) for match in found if match is not None]


def wait_for_recordings_decoded(page: Page, count: int) -> None:
    """Waits until the page has decoded `count` recordings, which is when its voice can say any word at once."""
    page.wait_for_function("count => window.recordingsDecoded >= count", arg=count)


def wait_for_recordings_started(page: Page, count: int) -> None:
    page.wait_for_function("count => window.recordingsStarted.length >= count", arg=count)
