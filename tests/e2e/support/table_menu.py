"""The table's menu: every table matter that is not the game's next decision lies behind its key."""

from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import FrameLocator, Locator, Page

MENU_KEY = ".menu-key"
MENU = ".anchored-panel:has(.menu)"
GIVE_UP_ROW = ".row.give-up"


def open_table_menu(person: Page | FrameLocator) -> Locator:
    """The table's menu with its key tapped open; an open one stays open."""
    menu = person.locator(MENU)
    if not menu.is_visible():
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
