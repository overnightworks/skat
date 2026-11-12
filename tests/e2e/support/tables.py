import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from playwright.sync_api import expect

from skat.table.records import TABLE_ID_PATTERN
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer

OPEN_TABLE = text(SOURCE_LANGUAGE, "start.openTable")
RUNNING_POINTS_SWITCH = text(SOURCE_LANGUAGE, "start.rulePoints")
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
TABLE_URL = re.compile(rf"{re.escape(TABLE_PAGE_PREFIX)}{TABLE_ID_PATTERN}$")


def click_new_table(person: Page, *, running_points: bool = False) -> str:
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    if running_points:
        person.get_by_role("switch", name=RUNNING_POINTS_SWITCH).click()
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person).to_have_url(TABLE_URL)
    return urlsplit(person.url).path


def open_new_table(person: Page, server: RunningServer, *, running_points: bool = False) -> str:
    person.goto(f"{server.base_url}/")
    return click_new_table(person, running_points=running_points)


def table_id_of(path: str) -> str:
    return path.removeprefix(TABLE_PAGE_PREFIX)


def watch(person: Page, server: RunningServer, path: str) -> None:
    person.goto(f"{server.base_url}{path}")
    expect(person.locator(".chair")).to_have_count(3)


def plate_of(person: Page, seat: int):
    return person.locator(f".chair[data-seat='{seat}'] .plate")


def sit_in(person: Page, seat: int) -> None:
    person.locator(f".chair[data-seat='{seat}']").get_by_role("button", name=SIT_DOWN).click()


def mark_page(person: Page) -> None:
    person.evaluate("window.keptAcrossUpdates = true")


def assert_never_reloaded(*people: Page) -> None:
    for person in people:
        assert person.evaluate("window.keptAcrossUpdates") is True
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
