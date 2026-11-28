"""The switch „Neuer Look (im Bau)“ shows the look under construction on the device that turned it on, only there."""

from functools import partial
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.looks import Look
from tests.e2e.support.people import DESKTOP
from tests.e2e.support.style import STYLE_KEY, STYLES, give_the_table_its_style
from tests.e2e.support.table_menu import menu_button
from tests.e2e.support.tables import open_new_table, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.records import TableStyle
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

NEW_LOOK = text(SOURCE_LANGUAGE, "table.newLook")
TABLE = text(SOURCE_LANGUAGE, "table.landmark")


@pytest.mark.parametrize("style", STYLES)
def test_a_seated_person_turns_the_new_look_on_for_this_device_alone_and_the_switch_on_it_brings_todays_surface_back(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], style: TableStyle
) -> None:
    on_todays_surface = partial(open_person, look=Look.TODAY, **DESKTOP)
    anna = record_page_errors(on_todays_surface(username="anna"), page_errors)
    path = open_new_table(anna, e2e_server)
    ben = record_page_errors(on_todays_surface(username="ben"), page_errors)
    watch(ben, e2e_server, path)
    give_the_table_its_style(anna, (anna, ben), style)
    new_surface = anna.get_by_role("main", name=TABLE)
    expect(new_surface).to_have_count(0)

    menu_button(anna, STYLE_KEY).click()
    anna.get_by_role("switch", name=NEW_LOOK).click()

    expect(new_surface).to_be_visible()
    expect(anna.get_by_role("switch", name=NEW_LOOK)).to_be_checked()
    expect(ben.get_by_role("main")).to_be_visible()
    expect(ben.get_by_role("main", name=TABLE)).to_have_count(0)

    anna.reload()

    expect(new_surface).to_be_visible()
    expect(anna.get_by_role("switch", name=NEW_LOOK)).to_be_checked()

    anna.get_by_role("switch", name=NEW_LOOK).click()

    expect(new_surface).to_have_count(0)
    expect(anna.get_by_role("main")).to_be_visible()
    menu_button(anna, STYLE_KEY).click()
    expect(anna.get_by_role("switch", name=NEW_LOOK)).not_to_be_checked()
