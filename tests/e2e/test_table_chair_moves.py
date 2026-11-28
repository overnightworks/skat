"""A chair that is taken, stood from or opened sounds in the sound set the player chose; a reload plays nothing, and a
device that asks for reduced motion hears the chair too.
"""

import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import tap, voices_started
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.declaring import reload_and_wait
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, WIDTHS
from tests.e2e.support.table_menu import menu_button
from tests.e2e.support.tables import SIT_DOWN, open_new_table, plate_of, sit_in, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SETTINGS_KEY = "skat.settings"
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SIT_QUESTION = text(SOURCE_LANGUAGE, "table.sitQuestion")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
# The sound set the table is heard in, one for each width.
SOUND_SET_AT_WIDTH = [
    pytest.param(WIDTHS[0].values[0], "leise", id="360-leise"),
    pytest.param(WIDTHS[1].values[0], "stammtisch", id="390-stammtisch"),
    pytest.param(WIDTHS[2].values[0], "funkeln", id="1280-funkeln"),
]


def page_with_settings(
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    *,
    stored: dict[str, Any],
    device_motion: str = "no-preference",
) -> Page:
    """A page that shows the table by the settings it stored."""
    page = record_page_errors(open_person(reduced_motion=device_motion, **form_factor), page_errors)
    page.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    return page


def sounded_since(page: Page, before: int) -> list[dict[str, Any]]:
    return voices_started(page)[before:]


def lobby_with_onlooker(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    **settings: Any,
) -> tuple[Page, Page]:
    """Anna sits at a table between hands, Ben watches beside it; the page with the settings is the onlooker's."""
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    sitter = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(sitter, e2e_server, path)
    onlooker = page_with_settings(open_person, page_errors, form_factor, **settings)
    watch(onlooker, e2e_server, path)
    tap(onlooker)
    return sitter, onlooker


@pytest.mark.parametrize(("form_factor", "sound_set"), SOUND_SET_AT_WIDTH)
def test_a_person_sits_and_stands_between_hands_and_the_chair_sounds_in_the_chosen_set_and_softer_as_it_empties(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    sound_set: str,
) -> None:
    sitter, onlooker = lobby_with_onlooker(
        open_person, e2e_server, page_errors, form_factor, stored={"soundSet": sound_set}
    )
    assert voices_started(onlooker) == []

    sit_in(sitter, 2)

    expect(plate_of(onlooker, 2)).to_have_text("ben")
    sat = voices_started(onlooker)
    assert sat != []

    menu_button(sitter, STAND_UP).click()

    expect(plate_of(onlooker, 2)).to_have_text(SEAT_FREE)
    stood = sounded_since(onlooker, len(sat))
    assert stood != []
    assert max(voice["gain"] for voice in stood) < max(voice["gain"] for voice in sat)
    assert page_errors == []


def test_a_reload_after_a_chair_changed_hands_sounds_nothing(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    sitter, onlooker = lobby_with_onlooker(open_person, e2e_server, page_errors, DESKTOP, stored={})
    sit_in(sitter, 2)
    expect(plate_of(onlooker, 2)).to_have_text("ben")

    reload_and_wait(onlooker)
    tap(onlooker)

    expect(plate_of(onlooker, 2)).to_have_text("ben")
    assert voices_started(onlooker) == []
    assert page_errors == []


def test_a_device_that_asks_for_reduced_motion_hears_the_chair_that_is_taken(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    sitter, onlooker = lobby_with_onlooker(
        open_person, e2e_server, page_errors, PHONE, stored={}, device_motion="reduce"
    )

    sit_in(sitter, 2)

    expect(plate_of(onlooker, 2)).to_have_text("ben")
    assert voices_started(onlooker) != []
    assert page_errors == []


@pytest.mark.parametrize(("form_factor", "sound_set"), SOUND_SET_AT_WIDTH)
def test_a_chair_of_the_running_hand_opens_and_is_taken_again_and_both_sound_in_the_chosen_set(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    sound_set: str,
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, PHONE)
    leaver_seat = table.seat_at["rearhand"]
    onlooker = page_with_settings(open_person, page_errors, form_factor, stored={"soundSet": sound_set})
    watch(onlooker, e2e_server, urlsplit(table.watcher.url).path)
    tap(onlooker)

    table.stand_up_through_the_api(leaver_seat)

    expect(plate_of(onlooker, leaver_seat)).to_have_text(SEAT_FREE)
    opened = voices_started(onlooker)
    assert opened != []
    if sound_set == "funkeln":
        assert {voice["kind"] for voice in opened} == {"tone"}
        assert len({voice["start"] for voice in opened}) == 2

    watcher = table.watcher
    sit_in(watcher, leaver_seat)
    watcher.get_by_role("dialog", name=SIT_QUESTION).get_by_role("button", name=SIT_DOWN).click()

    expect(plate_of(onlooker, leaver_seat)).not_to_have_text(SEAT_FREE)
    assert len(voices_started(onlooker)) > len(opened)
    assert page_errors == []
