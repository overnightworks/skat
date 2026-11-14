import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

FELT_FACE = ".trick .laid .face"
LANDING = "land-verspielt"
LANDING_QUIETLY = "land-dezent"
STILL = "none"
MOTION = "no-preference"
# The key the player's choices are kept under in the browser.
SETTINGS_KEY = "skat.settings"


@pytest.fixture
def deal_a_playing_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")

    return deal


def open_watcher_with_motion(
    open_person: Callable[..., Page],
    page_errors: list[str],
    table: PlayingTable,
    form_factor: dict[str, Any],
    *,
    device_motion: str = MOTION,
    stored: dict[str, Any] | None = None,
) -> Page:
    watcher = record_page_errors(open_person(reduced_motion=device_motion, **form_factor), page_errors)
    if stored is not None:
        watcher.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    return watcher


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_card_played_while_the_page_watches_lands_on_the_felt(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    watcher = open_watcher_with_motion(open_person, page_errors, table, form_factor)

    table.play_out(1)

    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    expect(watcher.locator(FELT_FACE)).to_have_css("animation-name", LANDING)
    expect(table.watcher.locator(FELT_FACE)).to_have_css("animation-name", STILL)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_cards_a_page_did_not_see_played_stand_still_and_the_next_card_lands(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    table.play_out(1)
    joined = open_watcher_with_motion(open_person, page_errors, table, form_factor)
    expect(joined.locator(FELT_FACE)).to_have_css("animation-name", STILL)

    joined.reload()
    expect(joined.locator(".chair")).to_have_count(3)
    expect(joined.locator(FELT_FACE)).to_have_css("animation-name", STILL)

    table.play_out(1)

    expect(joined.locator(FELT_FACE)).to_have_count(2)
    expect(joined.locator(FELT_FACE).last).to_have_css("animation-name", LANDING)
    expect(joined.locator(FELT_FACE).first).to_have_css("animation-name", STILL)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize(
    ("device_motion", "stored", "landing"),
    [
        (MOTION, {"motionSet": "dezent"}, LANDING_QUIETLY),
        (MOTION, {"motionSet": "verspielt"}, LANDING),
        ("reduce", {"motionSet": "dezent"}, STILL),
        ("reduce", {"motionSet": "dezent", "replayMotion": True}, LANDING_QUIETLY),
        ("reduce", {"replayMotion": True}, LANDING),
        (MOTION, {"replayMotion": False}, LANDING),
    ],
    ids=[
        "dezent",
        "verspielt",
        "reduced",
        "reduced-but-overridden-dezent",
        "reduced-but-overridden",
        "moving-no-override",
    ],
)
def test_a_card_lands_in_the_picked_set_and_the_device_asking_for_reduced_motion_stills_it_unless_the_player_overrides(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    device_motion: str,
    stored: dict[str, Any],
    landing: str,
) -> None:
    table = deal_a_playing_table(form_factor)
    watcher = open_watcher_with_motion(
        open_person, page_errors, table, form_factor, device_motion=device_motion, stored=stored
    )

    table.play_out(1)

    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    expect(watcher.locator(FELT_FACE)).to_have_css("animation-name", landing)
    assert page_errors == []
