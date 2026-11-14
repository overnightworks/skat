import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_HOLD_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, WORDS, text
from tests.e2e.support.audio import (
    recordings_started,
    tap,
    voices_started,
    wait_for_recordings_decoded,
    wait_for_recordings_started,
)
from tests.e2e.support.declaring import DeclaringTable, reload_and_wait
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.kontra import KONTRA_OPTIONS, say_kontra_as_an_opponent
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_table_with_options

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

# The key the player's choice is kept under in the browser.
SETTINGS_KEY = "skat.settings"
SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
VOICE = text(SOURCE_LANGUAGE, "sound.voice")
# The file of a recording is named by its catalog key and a hash of its bytes, after a dot.
RECORDED_KEY = re.compile(r"/(voice\.\w+)\.[\w-]+\.mp3$")
# The recordings of the page's language, which the page decodes once its voice is on.
RECORDING_COUNT = sum(key.startswith("voice.") for key in WORDS[SOURCE_LANGUAGE])
# The voices one bid or one word of Kontra start in each sound set, at the table's first tap.
BID_TAP_VOICES = {"leise": 2, "stammtisch": 1, "funkeln": 2}
KONTRA_KNOCK_VOICES = {"leise": 6, "stammtisch": 7, "funkeln": 7}
OPENING_BID, RAISED_BID = VALID_BIDS[0], VALID_BIDS[-1]


def table_with_settings(stored: dict[str, object], *, kontra: bool = False) -> type[DeclaringTable]:
    """A table whose watcher has `stored` in its browser and has tapped once before the auction begins.

    The auction is a bid, a hold, a raise and two passes, so the watcher sees every kind of word.
    """

    class VoicedTable(DeclaringTable):
        @staticmethod
        def _open_table(
            opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember], *, running_points: bool
        ) -> str:
            assert not running_points
            options = {"kontra": KONTRA_OPTIONS} if kontra else {}
            return open_table_with_options(opener, server, RawSession(server, member_of(opener)), options)

        def _win_the_auction(self, seat_at: dict[str, int]) -> None:
            self.watcher.evaluate(
                "([key, record]) => localStorage.setItem(key, record)", [SETTINGS_KEY, json.dumps(stored)]
            )
            reload_and_wait(self.watcher)
            tap(self.watcher)
            if stored.get("voice"):
                wait_for_recordings_decoded(self.watcher, RECORDING_COUNT)
            self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=OPENING_BID)
            self.step(seat_at["forehand"], TABLE_AUCTION_HOLD_SUFFIX)
            self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=RAISED_BID)
            self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
            self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)

    return VoicedTable


def deal(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    stored: dict[str, object],
    *,
    form_factor: dict[str, Any] = PHONE,
    kontra: bool = False,
) -> PlayingTable:
    return deal_playing_table(
        open_person,
        e2e_server,
        member_of,
        page_errors,
        form_factor,
        declaring=table_with_settings(stored, kontra=kontra),
    )


def keys_said(page: Page) -> list[str]:
    """The catalog keys of the recordings the page played, in the order they started."""
    found = [RECORDED_KEY.search(recording["url"]) for recording in recordings_started(page)]
    return [match.group(1) for match in found if match is not None]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_the_voice_on_the_watcher_hears_each_bid_and_pass_from_its_recording(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, {"voice": True}, form_factor=form_factor)

    assert keys_said(table.watcher) == [
        f"voice.value{OPENING_BID}",
        f"voice.value{OPENING_BID}",
        f"voice.value{RAISED_BID}",
        "voice.pass",
        "voice.pass",
    ]
    assert page_errors == []


@pytest.mark.parametrize(
    "stored",
    [{"voice": False}, {"voice": True, "muted": True}, {}],
    ids=["voice off", "sound off", "default"],
)
def test_without_the_voice_or_without_the_sound_nothing_is_said(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    stored: dict[str, object],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, stored)

    assert (len(voices_started(table.watcher)) > 0) is (not stored.get("muted"))
    assert recordings_started(table.watcher) == []
    assert page_errors == []


def test_a_reload_says_nothing(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, {"voice": True})
    assert len(keys_said(table.watcher)) == 5

    reload_and_wait(table.watcher)
    tap(table.watcher)

    assert recordings_started(table.watcher) == []
    assert voices_started(table.watcher) == []
    assert page_errors == []


@pytest.mark.parametrize("sound_set", BID_TAP_VOICES)
def test_a_word_of_kontra_knocks_in_every_sound_set_and_is_said_with_the_voice_on(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    sound_set: str,
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, {"voice": True, "soundSet": sound_set}, kontra=True)
    assert len(keys_said(table.watcher)) == 5
    before = len(voices_started(table.watcher))

    say_kontra_as_an_opponent(table)

    wait_for_recordings_started(table.watcher, 6)
    assert keys_said(table.watcher)[5:] == ["voice.kontra"]
    assert len(voices_started(table.watcher)) - before == KONTRA_KNOCK_VOICES[sound_set]
    assert page_errors == []


def test_the_switch_in_the_sound_panel_turns_the_voice_on_and_keeps_the_choice(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, {})
    watcher = table.watcher
    switch = watcher.get_by_role("switch", name=VOICE)

    watcher.locator(".sound-button").click()
    expect(switch).not_to_be_checked()
    switch.set_checked(True)
    reload_and_wait(watcher)
    watcher.locator(".sound-button").click()

    expect(watcher.get_by_role("switch", name=VOICE)).to_be_checked()
    assert json.loads(watcher.evaluate("key => localStorage.getItem(key)", SETTINGS_KEY))["voice"] is True
