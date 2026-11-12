from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

RECORDING_AUDIO_SCRIPT = Path(__file__).with_name("recording_audio.js")


def voices_started(page: Page) -> list[dict[str, Any]]:
    """The voices the page started on the recording stand-in for Web Audio, in the order they started."""
    return page.evaluate("window.voicesStarted")
