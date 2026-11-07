import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from playwright.sync_api import expect

from skat.web.tables import TABLE_PAGE_PREFIX
from tests.e2e.support.browser import NEW_TABLE_BUTTON

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer

TABLE_URL = re.compile(rf"{re.escape(TABLE_PAGE_PREFIX)}[0-9a-f]{{32}}$")


def click_new_table(person: Page) -> str:
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    expect(person).to_have_url(TABLE_URL)
    return urlsplit(person.url).path


def open_new_table(person: Page, server: RunningServer) -> str:
    person.goto(f"{server.base_url}/")
    return click_new_table(person)


def table_id_of(path: str) -> str:
    return path.removeprefix(TABLE_PAGE_PREFIX)
