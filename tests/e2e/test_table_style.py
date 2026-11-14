from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import tap
from tests.e2e.support.people import WIDTHS

if TYPE_CHECKING:
    from tests.e2e.support.hands import PlayingTable

pytestmark = pytest.mark.e2e

STYLE_KEY = text(SOURCE_LANGUAGE, "table.styleName")
STRANDBAR = text(SOURCE_LANGUAGE, "table.styleStrandbar")
KLASSIK = text(SOURCE_LANGUAGE, "table.styleKlassik")
SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
ROOM = ".room"
BEACH = ".beach"


def choose_style(person: Page, name: str) -> None:
    person.get_by_role("button", name=STYLE_KEY).click()
    person.locator(".style-tile", has_text=name).click()
    person.keyboard.press("Escape")


def sea_levels(page: Page) -> list[float]:
    return page.evaluate("window.seaLevels")


def test_a_table_is_classic_until_a_seated_person_changes_it(table: PlayingTable) -> None:
    for person in table.everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", "klassik")
        expect(person.locator(BEACH)).to_have_count(0)


def test_a_seated_person_changes_the_style_for_every_page_at_the_table_and_it_stays_after_a_reload(
    table: PlayingTable,
) -> None:
    chooser = table.pages[table.seat_at["forehand"]]

    choose_style(chooser, STRANDBAR)

    for person in table.everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", "strandbar")
        expect(person.locator(BEACH)).not_to_have_count(0)
    table.watcher.reload()
    expect(table.watcher.locator(ROOM)).to_have_attribute("data-style", "strandbar")

    choose_style(table.pages[table.seat_at["rearhand"]], KLASSIK)

    for person in table.everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", "klassik")
        expect(person.locator(BEACH)).to_have_count(0)


def test_a_watcher_has_no_key_for_the_style(table: PlayingTable) -> None:
    expect(table.watcher.get_by_role("button", name=STYLE_KEY)).to_have_count(0)
    expect(table.pages[table.seat_at["forehand"]].get_by_role("button", name=STYLE_KEY)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_sea_runs_under_the_tables_style_after_a_tap_and_follows_the_mute(
    table: PlayingTable, form_factor: dict[str, Any]
) -> None:
    watcher = table.watcher
    watcher.set_viewport_size(form_factor["viewport"])
    choose_style(table.pages[table.seat_at["forehand"]], STRANDBAR)
    expect(watcher.locator(ROOM)).to_have_attribute("data-style", "strandbar")
    assert watcher.evaluate("window.seaStarts") == 0

    tap(watcher)

    watcher.wait_for_function("window.seaStarts > 0")
    assert sea_levels(watcher)[-1] > 0
    watcher.get_by_role("button", name=SOUND_PANEL).click()
    watcher.get_by_role("switch", name=TONE).set_checked(False)
    watcher.wait_for_function("window.seaLevels.at(-1) === 0")

    choose_style(table.pages[table.seat_at["forehand"]], KLASSIK)
    expect(watcher.locator(ROOM)).to_have_attribute("data-style", "klassik")
    assert sea_levels(watcher)[-1] == 0
