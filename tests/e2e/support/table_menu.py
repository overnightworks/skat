"""The table's menu: every table matter that is not the game's next decision lies behind its key."""

from contextlib import nullcontext
from typing import TYPE_CHECKING

from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.tables import until_the_agents_are_read

if TYPE_CHECKING:
    from playwright.sync_api import FrameLocator, Locator

MENU_KEY = old_surface.MENU_KEY
MENU = old_surface.TABLE_MENU
GIVE_UP_ROW = old_surface.GIVE_UP_ROW
SHORTEN_ROW = old_surface.SHORTEN_ROW
PLAY_OPEN_ROW = old_surface.PLAY_OPEN_ROW
AGENTS = text(SOURCE_LANGUAGE, "table.agents")
AGENTS_PANEL = old_surface.AGENTS_PANEL
# The open agents' list keeps this far from either edge of the viewport, in pixels.
EDGE_MARGIN = 16
ACCOUNT = text(SOURCE_LANGUAGE, "account.title")
ACCOUNT_PANEL = old_surface.ACCOUNT_PANEL


def open_table_menu(person: Page | FrameLocator) -> Locator:
    """The table's menu with its key tapped open; an open one stays open.

    Opening the menu reads the agents anew; a page waits for that answer, which a table closed meanwhile would
    answer 404 and the browser would log.
    """
    menu = old_surface.table_menu(person)
    if not menu.is_visible():
        with until_the_agents_are_read(person) if isinstance(person, Page) else nullcontext():
            old_surface.menu_key(person).click()
    expect(menu).to_be_visible()
    return menu


def close_table_menu(person: Page) -> None:
    """The table's menu closed by Escape, the way a person dismisses it."""
    person.keyboard.press("Escape")
    expect(old_surface.table_menu(person)).to_be_hidden()


def menu_button(person: Page | FrameLocator, name: str) -> Locator:
    """The menu's button of this exact name, with the menu opened first."""
    return open_table_menu(person).get_by_role("button", name=name, exact=True)


def open_agents_panel(person: Page | FrameLocator) -> Locator:
    """The panel of the agents, opened by the menu's „Agenten“ row; an open one stays open."""
    panel = old_surface.agents_panel(person)
    if not panel.is_visible():
        menu_button(person, AGENTS).click()
    expect(panel).to_be_visible()
    return panel


def open_account_panel(person: Page | FrameLocator) -> Locator:
    """The panel of the account with the legal links, opened by the menu's account row."""
    menu_button(person, ACCOUNT).click()
    panel = old_surface.account_panel(person)
    expect(panel).to_be_visible()
    return panel


def menu_row(person: Page | FrameLocator, row: str) -> Locator:
    """The menu's row of this selector, with the menu opened first."""
    return open_table_menu(person).locator(row)
