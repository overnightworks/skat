"""A chair that is taken, stood from or opened moves in the motion set and sounds in the sound set the player chose;
a reload plays nothing, and a device that asks for reduced motion keeps the chair still but not silent.
"""

import itertools
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.seating import TABLE_STAND_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import tap, voices_started
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, WIDTHS
from tests.e2e.support.tables import SIT_DOWN, open_new_table, plate_of, sit_in

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SETTINGS_KEY = "skat.settings"
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SIT_QUESTION = text(SOURCE_LANGUAGE, "table.sitQuestion")
# The sound set and the motion set the table is shown in, one pair for each width.
SETS_AT_WIDTH = [
    pytest.param(WIDTHS[0].values[0], "leise", "dezent", id="360-leise-dezent"),
    pytest.param(WIDTHS[1].values[0], "stammtisch", "verspielt", id="390-stammtisch-verspielt"),
    pytest.param(WIDTHS[2].values[0], "funkeln", "verspielt", id="1280-funkeln-verspielt"),
]
# The seconds a chair that is taken, and one that empties, move in each motion set; the set's CSS keeps the same time.
SIT_SECONDS = {"dezent": 0.9, "verspielt": 1.4}
EMPTY_SECONDS = {"dezent": 0.3, "verspielt": 0.4}
SITTING = "chair-taken"
STANDING = "chair-stood"
OPENING = "chair-opened"
# An installed clock keeps ticking until paused, and pausing only moves time forward, so it stops this far ahead.
CLOCK_HOLD_LEAD = timedelta(seconds=5)
command_numbers = itertools.count(1)


def held_page(
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    *,
    stored: dict[str, Any],
    device_motion: str = "no-preference",
) -> Page:
    """A page that shows the table by the settings it stored, with a clock only the test moves."""
    page = record_page_errors(open_person(reduced_motion=device_motion, **form_factor), page_errors)
    page.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    page.clock.install()
    page.clock.pause_at(datetime.now(UTC) + CLOCK_HOLD_LEAD)
    return page


def chair_of(page: Page, seat: int):
    return page.locator(f".chair[data-seat='{seat}']")


def animation_of(page: Page, seat: int) -> str:
    return chair_of(page, seat).locator(".tile").first.evaluate("tile => getComputedStyle(tile).animationName")


def sounded_since(page: Page, before: int) -> list[dict[str, Any]]:
    return voices_started(page)[before:]


def stand_up_through_the_api(table: PlayingTable, seat: int) -> None:
    table.declaring.sessions[seat].post(
        f"{table.declaring.api_path}{TABLE_STAND_SUFFIX}", {"command_id": f"stand-{next(command_numbers):04d}"}
    )


def lobby_with_onlooker(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    **settings: Any,
) -> tuple[Page, Page]:
    """Anna sits at a table between hands, Ben watches beside it; the held page is the onlooker's."""
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    sitter = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    sitter.goto(f"{e2e_server.base_url}{path}")
    onlooker = held_page(open_person, page_errors, form_factor, **settings)
    onlooker.goto(f"{e2e_server.base_url}{path}")
    expect(onlooker.locator(".chair")).to_have_count(3)
    tap(onlooker)
    return sitter, onlooker


@pytest.mark.parametrize(("form_factor", "sound_set", "motion_set"), SETS_AT_WIDTH)
def test_a_person_sits_and_stands_between_hands_and_the_chair_moves_and_knocks_in_the_chosen_sets(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    sound_set: str,
    motion_set: str,
) -> None:
    sitter, onlooker = lobby_with_onlooker(
        open_person,
        e2e_server,
        page_errors,
        form_factor,
        stored={"soundSet": sound_set, "motionSet": motion_set},
    )
    assert voices_started(onlooker) == []

    sit_in(sitter, 2)

    expect(chair_of(onlooker, 2)).to_have_attribute("data-moving", SITTING)
    expect(plate_of(onlooker, 2)).to_have_text("ben")
    assert animation_of(onlooker, 2) == f"sit-{motion_set}"
    expect(chair_of(onlooker, 2).locator(".tile")).to_have_css("animation-duration", f"{SIT_SECONDS[motion_set]}s")
    expect(chair_of(onlooker, 1)).not_to_have_attribute("data-moving", SITTING)
    sat = voices_started(onlooker)
    assert sat != []
    onlooker.clock.run_for(int(SIT_SECONDS[motion_set] * 1000) - 100)
    expect(chair_of(onlooker, 2)).to_have_attribute("data-moving", SITTING)
    onlooker.clock.run_for(100)
    expect(chair_of(onlooker, 2)).not_to_have_attribute("data-moving", SITTING)

    sitter.get_by_role("button", name=STAND_UP).click()

    expect(chair_of(onlooker, 2)).to_have_attribute("data-moving", STANDING)
    expect(plate_of(onlooker, 2)).to_have_text(text(SOURCE_LANGUAGE, "table.seatFree"))
    assert animation_of(onlooker, 2) == f"empty-{motion_set}"
    expect(chair_of(onlooker, 2).locator(".tile")).to_have_css("animation-duration", f"{EMPTY_SECONDS[motion_set]}s")
    stood = sounded_since(onlooker, len(sat))
    assert stood != []
    assert max(voice["gain"] for voice in stood) < max(voice["gain"] for voice in sat)
    onlooker.clock.run_for(int(EMPTY_SECONDS[motion_set] * 1000))
    expect(chair_of(onlooker, 2)).not_to_have_attribute("data-moving", STANDING)
    assert page_errors == []


def test_a_reload_after_a_chair_changed_hands_moves_and_sounds_nothing(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    sitter, onlooker = lobby_with_onlooker(open_person, e2e_server, page_errors, DESKTOP, stored={})
    sit_in(sitter, 2)
    expect(chair_of(onlooker, 2)).to_have_attribute("data-moving", SITTING)

    onlooker.reload()
    expect(onlooker.locator(".chair")).to_have_count(3)
    tap(onlooker)

    expect(plate_of(onlooker, 2)).to_have_text("ben")
    expect(onlooker.locator(".chair[data-moving]")).to_have_count(0)
    assert voices_started(onlooker) == []
    assert page_errors == []


@pytest.mark.parametrize(
    ("stored", "moves"),
    [({}, False), ({"replayMotion": True}, True)],
    ids=["reduced-motion-keeps-the-chair-still", "override-moves-it-anyway"],
)
def test_a_device_that_asks_for_reduced_motion_keeps_the_chair_still_unless_the_player_overrides_and_the_sound_plays(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    stored: dict[str, Any],
    moves: bool,
) -> None:
    sitter, onlooker = lobby_with_onlooker(
        open_person, e2e_server, page_errors, PHONE, stored=stored, device_motion="reduce"
    )

    sit_in(sitter, 2)

    expect(plate_of(onlooker, 2)).to_have_text("ben")
    assert animation_of(onlooker, 2) == ("sit-verspielt" if moves else "none")
    expect(onlooker.locator(".chair[data-moving]")).to_have_count(1 if moves else 0)
    assert voices_started(onlooker) != []
    assert page_errors == []


@pytest.mark.parametrize(("form_factor", "sound_set", "motion_set"), SETS_AT_WIDTH)
def test_a_chair_of_the_running_hand_opens_and_is_taken_again_and_both_move_and_sound_in_the_chosen_sets(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    sound_set: str,
    motion_set: str,
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, PHONE)
    leaver_seat = table.seat_at["rearhand"]
    onlooker = held_page(open_person, page_errors, form_factor, stored={"soundSet": sound_set, "motionSet": motion_set})
    onlooker.goto(table.watcher.url)
    expect(onlooker.locator(".chair")).to_have_count(3)
    tap(onlooker)

    stand_up_through_the_api(table, leaver_seat)

    expect(chair_of(onlooker, leaver_seat)).to_have_attribute("data-moving", OPENING)
    assert animation_of(onlooker, leaver_seat) == f"empty-{motion_set}"
    opened = voices_started(onlooker)
    assert opened != []
    if sound_set == "funkeln":
        assert {voice["kind"] for voice in opened} == {"tone"}
        assert len({voice["start"] for voice in opened}) == 2
    onlooker.clock.run_for(int(EMPTY_SECONDS[motion_set] * 1000))
    expect(chair_of(onlooker, leaver_seat)).not_to_have_attribute("data-moving", OPENING)

    watcher = table.watcher
    chair_of(watcher, leaver_seat).get_by_role("button", name=SIT_DOWN).click()
    watcher.get_by_role("dialog", name=SIT_QUESTION).get_by_role("button", name=SIT_DOWN).click()

    expect(chair_of(onlooker, leaver_seat)).to_have_attribute("data-moving", SITTING)
    assert animation_of(onlooker, leaver_seat) == f"sit-{motion_set}"
    assert len(voices_started(onlooker)) > len(opened)
    assert page_errors == []
