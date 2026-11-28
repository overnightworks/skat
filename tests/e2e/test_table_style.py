from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.table.records import TableStyle
from skat.web.style import TABLE_STYLE_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.audio import tap
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.passed_in_series import refuse
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.style import STYLE_KEY, choose_style
from tests.e2e.support.table_menu import menu_button, open_table_menu

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SOUND_PANEL = text(SOURCE_LANGUAGE, "sound.panelName")
TONE = text(SOURCE_LANGUAGE, "sound.tone")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
KLASSIK = TableStyle.KLASSIK.value
STRANDBAR = TableStyle.STRANDBAR.value


def sea_levels(page: Page) -> list[float]:
    return page.evaluate("window.seaLevels")


def test_a_table_is_classic_until_a_seated_person_changes_it(table: PlayingTable) -> None:
    for person in table.everyone:
        old_surface.expect_the_style(person, KLASSIK)


def test_a_seated_person_changes_the_style_for_every_page_at_the_table_and_it_stays_after_a_reload(
    table: PlayingTable,
) -> None:
    chooser = table.pages[table.seat_at["forehand"]]

    choose_style(chooser, TableStyle.STRANDBAR)

    for person in table.everyone:
        old_surface.expect_the_style(person, STRANDBAR)
    table.watcher.reload()
    old_surface.expect_the_style(table.watcher, STRANDBAR)

    choose_style(table.pages[table.seat_at["rearhand"]], TableStyle.KLASSIK)

    for person in table.everyone:
        old_surface.expect_the_style(person, KLASSIK)


def test_a_watcher_has_no_key_for_the_style(table: PlayingTable) -> None:
    expect(open_table_menu(table.watcher).get_by_role("button", name=STYLE_KEY, exact=True)).to_have_count(0)
    expect(menu_button(table.pages[table.seat_at["forehand"]], STYLE_KEY)).to_be_visible()


def test_the_sea_runs_under_the_tables_style_after_a_tap_and_follows_the_mute(table: PlayingTable) -> None:
    watcher = table.watcher
    choose_style(table.pages[table.seat_at["forehand"]], TableStyle.STRANDBAR)
    old_surface.expect_the_style(watcher, STRANDBAR)
    assert watcher.evaluate("window.seaStarts") == 0

    tap(watcher)

    watcher.wait_for_function("window.seaStarts > 0")
    assert sea_levels(watcher)[-1] > 0
    watcher.get_by_role("button", name=SOUND_PANEL).click()
    watcher.get_by_role("switch", name=TONE).set_checked(False)
    watcher.wait_for_function("window.seaLevels.at(-1) === 0")

    choose_style(table.pages[table.seat_at["forehand"]], TableStyle.KLASSIK)
    old_surface.expect_the_style(watcher, KLASSIK)
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
    old_surface.style_tile(chooser, STRANDBAR).click()

    expect(chooser.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    expect(old_surface.style_tile(chooser, KLASSIK).get_by_role("radio")).to_be_checked()
    old_surface.expect_the_style(chooser, KLASSIK)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_style_panel_offers_every_style_and_changes_the_table_at_every_width(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")
    chooser = table.pages[table.seat_at["forehand"]]

    menu_button(chooser, STYLE_KEY).click()

    styles = chooser.get_by_role("radiogroup", name=STYLE_KEY, exact=True).get_by_role("radio")
    expect(styles).to_have_count(len(TableStyle))
    old_surface.style_tile(chooser, STRANDBAR).click()
    for person in table.everyone:
        old_surface.expect_the_style(person, STRANDBAR)
    chooser.keyboard.press("Escape")
    expect(menu_button(chooser, STYLE_KEY)).to_be_visible()
    assert page_errors == []
