from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.table.records import TableStyle
from skat.web.style import TABLE_STYLE_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import tap
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.kontra import ContestedTable
from tests.e2e.support.passed_in_series import refuse
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.style import ROOM, STYLE_KEY, TABLE_SCENES, choose_style, expect_painted_as_the_scene
from tests.e2e.support.table_menu import close_table_menu, menu_button, open_table_menu

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import BrowserContext

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
BEACH = ".beach"
STYLE_TILES = ".style-tile"
SCENE_STYLE_ROW = ".snd-row.look"
PAGE_STYLE_ROW = ".style-row"
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
REFUSED = 409
# The thirtieth card ends the hand.
CARDS_IN_A_HAND = 30
KEY_COLOUR = "key => getComputedStyle(key).backgroundColor"
SCENE_KEY_DRAWN = """id => { const frame = document.getElementById(id);
  const key = frame.querySelector('.button-stage'); const drawn = getComputedStyle(key);
  const edge = frame.getBoundingClientRect(); const box = key.getBoundingClientRect();
  return {background: drawn.backgroundColor, color: drawn.color, height: drawn.height, transform: drawn.transform,
          left: box.left - edge.left, top: box.top - edge.top}; }"""


def the_weiter_key(table: PlayingTable) -> tuple[Page, str]:
    """The declarer's page at the Strandbar once the hand is played out, which waits on his „Weiter“."""
    choose_style(table.pages[table.declarer_seat], TableStyle.STRANDBAR)
    table.play_out(CARDS_IN_A_HAND)
    return table.pages[table.declarer_seat], ".copy.weiter"


def the_kontra_key(table: PlayingTable) -> tuple[Page, str]:
    """The page at the Strandbar of the opponent who bid, which the first card waits on for his Kontra.

    The style is offered only to a seated person who has no word to say, here the rearhand who passed at once.
    """
    choose_style(table.pages[table.seat_at["rearhand"]], TableStyle.STRANDBAR)
    return table.pages[table.seat_at["forehand"]], ".copy.kontra"


DECISION_KEYS = [
    pytest.param(DeclaringTable, the_weiter_key, id="weiter"),
    pytest.param(ContestedTable, the_kontra_key, id="kontra"),
]


def expect_the_row_in_the_menu(person: Page) -> None:
    """The style row is visible in the table's menu and lies within the menu's box."""
    menu = open_table_menu(person)
    row = menu_button(person, STYLE_KEY)
    expect(row).to_be_visible()
    row_box = row.bounding_box()
    menu_box = menu.bounding_box()
    assert row_box is not None
    assert menu_box is not None
    assert row_box["x"] >= menu_box["x"]
    assert row_box["x"] + row_box["width"] <= menu_box["x"] + menu_box["width"]
    assert row_box["y"] >= menu_box["y"]
    assert row_box["y"] + row_box["height"] <= menu_box["y"] + menu_box["height"]
    close_table_menu(person)


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
    expect(table.watcher.locator(".row.style")).to_have_count(0)
    expect_the_row_in_the_menu(table.pages[table.seat_at["forehand"]])


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

    chooser.route(f"**{table.declaring.api_path}{TABLE_STYLE_SUFFIX}", refuse)
    menu_button(chooser, STYLE_KEY).click()
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

    expect_the_row_in_the_menu(chooser)
    menu_button(chooser, STYLE_KEY).click()

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
    expect_the_row_in_the_menu(chooser)
    assert page_errors == []


@pytest.mark.parametrize(("declaring", "decision_key"), DECISION_KEYS)
def test_the_key_the_table_waits_on_is_as_bright_in_the_strandbar_as_in_klassik(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    declaring: type[DeclaringTable],
    decision_key: Callable[[PlayingTable], tuple[Page, str]],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, PHONE, declaring=declaring)
    person, selector = decision_key(table)
    key = person.locator(selector)
    expect(person.locator(ROOM)).to_have_attribute("data-style", "strandbar")
    expect(key).to_be_visible()
    strandbar = key.evaluate(KEY_COLOUR)

    # The style is not offered while the table waits on a decision, so the Klassik stylesheet paints the same key here.
    person.locator(ROOM).evaluate("room => { room.dataset.style = 'klassik'; }")

    assert key.evaluate(KEY_COLOUR) == strandbar
    assert page_errors == []


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("scene", ["turn-pop", "strand-turn-pop"])
def test_the_pictures_turn_pop_scene_draws_the_waited_on_key_where_and_as_the_bid_scene_draws_it(
    new_context: Callable[..., BrowserContext], scene: str, width: int
) -> None:
    page = new_context(reduced_motion="reduce").new_page()
    page.goto(TABLE_SCENES.as_uri())

    assert page.evaluate(SCENE_KEY_DRAWN, f"{scene}-{width}") == page.evaluate(SCENE_KEY_DRAWN, f"bid-middle-{width}")
