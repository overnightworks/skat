import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy import select

from skat.store.schema import tables
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.tables import (
    click_new_table,
    mark_page,
    open_new_table,
    sit_in,
    table_id_of,
    watch,
    watchers_of,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

CLOSE_KEY = text(SOURCE_LANGUAGE, "table.close")
QUESTION = text(SOURCE_LANGUAGE, "table.closeQuestion")
CONFIRM = text(SOURCE_LANGUAGE, "table.closeConfirm")
CANCEL = text(SOURCE_LANGUAGE, "table.closeCancel")
DESKTOP_WIDTH = 900
ROUND_KEY_PIXELS = 52


def close_key(person: Page):
    return person.locator(".actions").get_by_role("button", name=CLOSE_KEY, exact=True)


def dialog_of(person: Page):
    return person.get_by_role("dialog", name=QUESTION)


def closer_name(server: RunningServer, person: Page, table_id: str) -> str:
    """The closer's stored name, read once the person's page shows that the table is closed."""
    closed = re.compile(re.escape(text(SOURCE_LANGUAGE, "closed.closedBy", name="")).strip())
    expect(person.get_by_role("heading", name=closed)).to_be_visible()
    with server.engine.connect() as connection:
        return connection.execute(select(tables.c.closed_by_name).where(tables.c.id == table_id)).scalar_one()


def expect_the_closed_face(person: Page, name: str) -> None:
    heading = text(SOURCE_LANGUAGE, "closed.closedBy", name=name)
    expect(person.get_by_role("heading", name=heading)).to_be_visible()
    expect(person.locator(".closed .glyph.by")).to_have_text(name[0])
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    expect(close_key(person)).to_have_count(0)


def seat_the_table(
    open_person: Callable[..., Page], server: RunningServer, errors: list[str], form_factor: dict[str, Any], seats: int
) -> tuple[dict[str, Page], str]:
    people = {
        name: record_page_errors(open_person(username=name, **form_factor), errors)
        for name in ("anna", "ben", "cleo", "dora")
    }
    path = open_new_table(people["anna"], server)
    for seat, name in zip(range(2, seats + 1), ("ben", "cleo"), strict=False):
        watch(people[name], server, path)
        sit_in(people[name], seat)
    watch(people["dora"], server, path)
    return people, path


@pytest.mark.parametrize("dealt", [False, True], ids=["undealt", "dealt"])
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_opener_closes_the_table_after_the_question_and_every_page_names_the_closer(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    dealt: bool,
) -> None:
    people, path = seat_the_table(open_person, e2e_server, page_errors, form_factor, 3 if dealt else 2)
    anna, ben, dora = people["anna"], people["ben"], people["dora"]
    for person in (anna, ben, dora):
        expect(watchers_of(person)).to_be_visible()
        mark_page(person)
    expect(close_key(ben)).to_have_count(0)
    expect(close_key(dora)).to_have_count(0)
    wide = form_factor["viewport"]["width"] >= DESKTOP_WIDTH
    key = close_key(anna).bounding_box()
    assert key is not None
    assert (key["width"] > ROUND_KEY_PIXELS) is wide

    close_key(anna).click()
    expect(dialog_of(anna)).to_be_visible()
    dialog_of(anna).get_by_role("button", name=CANCEL, exact=True).click()
    expect(dialog_of(anna)).to_have_count(0)
    expect(anna.locator(".chair")).to_have_count(3)
    expect(close_key(anna)).to_be_visible()

    close_key(anna).click()
    dialog_of(anna).get_by_role("button", name=CONFIRM, exact=True).click()

    name = closer_name(e2e_server, anna, table_id_of(path))
    for person in (anna, ben, dora):
        expect_the_closed_face(person, name)
    for person in (anna, ben, dora):
        assert person.evaluate("window.keptAcrossUpdates") is True


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_old_link_of_a_closed_table_names_the_closer_and_a_new_table_gets_a_new_id(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    anna = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    erik = record_page_errors(open_person(username="erik", **form_factor), page_errors)
    path = open_new_table(anna, e2e_server)
    close_key(anna).click()
    dialog_of(anna).get_by_role("button", name=CONFIRM, exact=True).click()
    name = closer_name(e2e_server, anna, table_id_of(path))
    expect_the_closed_face(anna, name)

    erik.goto(f"{e2e_server.base_url}{path}")
    expect_the_closed_face(erik, name)

    click_new_table(anna)
    expect(anna).not_to_have_url(f"{e2e_server.base_url}{path}")
