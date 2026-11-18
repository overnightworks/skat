"""The table's menu: every table matter that is not the game's next decision lies behind its key."""

from contextlib import nullcontext
from typing import TYPE_CHECKING

from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.tables import until_the_agents_are_read

if TYPE_CHECKING:
    from playwright.sync_api import FrameLocator, Locator

MENU_KEY = ".menu-key"
MENU = ".anchored-panel:has(.menu)"
GIVE_UP_ROW = ".row.give-up"
SHORTEN_ROW = ".row.shorten"
PLAY_OPEN_ROW = ".row.play-open"
AGENTS = text(SOURCE_LANGUAGE, "table.agents")
AGENTS_PANEL = ".anchored-panel:has(.agents-list)"


def open_table_menu(person: Page | FrameLocator) -> Locator:
    """The table's menu with its key tapped open; an open one stays open.

    Opening the menu reads the agents anew; a page waits for that answer, which a table closed meanwhile would
    answer 404 and the browser would log.
    """
    menu = person.locator(MENU)
    if not menu.is_visible():
        with until_the_agents_are_read(person) if isinstance(person, Page) else nullcontext():
            person.locator(MENU_KEY).click()
    expect(menu).to_be_visible()
    return menu


def close_table_menu(person: Page) -> None:
    """The table's menu closed by Escape, the way a person dismisses it."""
    person.keyboard.press("Escape")
    expect(person.locator(MENU)).to_be_hidden()


def menu_button(person: Page | FrameLocator, name: str) -> Locator:
    """The menu's button of this exact name, with the menu opened first."""
    return open_table_menu(person).get_by_role("button", name=name, exact=True)


def open_agents_panel(person: Page | FrameLocator) -> Locator:
    """The panel of the agents, opened by the menu's „Agenten“ row; an open one stays open."""
    panel = person.locator(AGENTS_PANEL)
    if not panel.is_visible():
        menu_button(person, AGENTS).click()
    expect(panel).to_be_visible()
    return panel


def menu_row(person: Page | FrameLocator, row: str) -> Locator:
    """The menu's row of this selector, with the menu opened first."""
    return open_table_menu(person).locator(row)
