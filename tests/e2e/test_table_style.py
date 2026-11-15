from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.table.records import TableStyle
from skat.web.style import TABLE_STYLE_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import tap
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.style import ROOM, STYLE_KEY, choose_style, expect_painted_as_the_scene

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Route

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
BEACH = ".beach"
STYLE_TILES = ".style-tile"
STRIP = ".actions"
SCENE_STYLE_ROW = ".snd-row.look"
PAGE_STYLE_ROW = ".style-row"
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
REFUSED = 409


def expect_the_key_in_the_strip(person: Page) -> None:
    """The style key is visible in the play strip and lies within the strip's box."""
    strip = person.locator(STRIP)
    key = strip.get_by_role("button", name=STYLE_KEY)
    expect(key).to_be_visible()
    key_box = key.bounding_box()
    strip_box = strip.bounding_box()
    assert key_box is not None
    assert strip_box is not None
    assert key_box["x"] >= strip_box["x"]
    assert key_box["x"] + key_box["width"] <= strip_box["x"] + strip_box["width"]
    assert key_box["y"] >= strip_box["y"]
    assert key_box["y"] + key_box["height"] <= strip_box["y"] + strip_box["height"]


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

    choose_style(chooser, TableStyle.STRANDBAR)

    for person in table.everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", "strandbar")
        expect(person.locator(BEACH)).not_to_have_count(0)
    table.watcher.reload()
    expect(table.watcher.locator(ROOM)).to_have_attribute("data-style", "strandbar")

    choose_style(table.pages[table.seat_at["rearhand"]], TableStyle.KLASSIK)

    for person in table.everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", "klassik")
        expect(person.locator(BEACH)).to_have_count(0)


def test_a_watcher_has_no_key_for_the_style(table: PlayingTable) -> None:
    expect(table.watcher.get_by_role("button", name=STYLE_KEY)).to_have_count(0)
    expect(table.pages[table.seat_at["forehand"]].get_by_role("button", name=STYLE_KEY)).to_be_visible()


def test_the_sea_runs_under_the_tables_style_after_a_tap_and_follows_the_mute(table: PlayingTable) -> None:
    watcher = table.watcher
    choose_style(table.pages[table.seat_at["forehand"]], TableStyle.STRANDBAR)
    expect(watcher.locator(ROOM)).to_have_attribute("data-style", "strandbar")
    assert watcher.evaluate("window.seaStarts") == 0

    tap(watcher)

    watcher.wait_for_function("window.seaStarts > 0")
    assert sea_levels(watcher)[-1] > 0
    watcher.get_by_role("button", name=SOUND_PANEL).click()
    watcher.get_by_role("switch", name=TONE).set_checked(False)
    watcher.wait_for_function("window.seaLevels.at(-1) === 0")

    choose_style(table.pages[table.seat_at["forehand"]], TableStyle.KLASSIK)
    expect(watcher.locator(ROOM)).to_have_attribute("data-style", "klassik")
    assert sea_levels(watcher)[-1] == 0


def test_a_refused_style_shows_the_failure_and_leaves_the_tables_style_marked(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    # The browser logs the refused choice as a console error; that refusal is the point of this test.
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    chooser = table.pages[table.seat_at["forehand"]]

    def refuse(route: Route) -> None:
        route.fulfill(status=REFUSED, content_type="application/json", body="{}")

    chooser.route(f"**{table.declaring.api_path}{TABLE_STYLE_SUFFIX}", refuse)
    chooser.get_by_role("button", name=STYLE_KEY).click()
    chooser.locator(f"{STYLE_TILES}.style-strandbar").click()

    expect(chooser.locator(".note")).to_have_text(COMMAND_FAILED)
    expect(chooser.locator(f"{STYLE_TILES}.style-klassik input")).to_be_checked()
    expect(chooser.locator(ROOM)).to_have_attribute("data-style", "klassik")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_style_panel_opens_inside_the_page_and_changes_the_table_at_every_width(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")
    chooser = table.pages[table.seat_at["forehand"]]

    expect_the_key_in_the_strip(chooser)
    chooser.get_by_role("button", name=STYLE_KEY).click()

    expect(chooser.locator(STYLE_TILES)).to_have_count(len(TableStyle))
    expect_painted_as_the_scene(
        chooser, "strand-choose", PAGE_STYLE_ROW, SCENE_STYLE_ROW, ["paddingTop", "paddingBottom"]
    )
    window = chooser.evaluate("({ width: window.innerWidth, height: window.innerHeight })")
    for tile in chooser.locator(STYLE_TILES).all():
        box = tile.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= window["width"]
        assert box["y"] >= 0
        assert box["y"] + box["height"] <= window["height"]
    chooser.locator(f"{STYLE_TILES}.style-strandbar").click()
    for person in table.everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", "strandbar")
    chooser.keyboard.press("Escape")
    expect_the_key_in_the_strip(chooser)
    assert page_errors == []
