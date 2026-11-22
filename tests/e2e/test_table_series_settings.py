from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from skat.table.records import SERIES_LENGTH_STEP
from skat.web.ready import TABLE_NEW_SERIES_SUFFIX, TABLE_NEXT_SETTINGS_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.passed_in_series import (
    CHANGE,
    COMMAND_FAILED,
    MORE_GAMES,
    NEXT_LINE,
    NEXT_SHEET,
    SAVE,
    SERIES_LENGTH,
    PassedInTable,
    pass_the_series_in,
    refuse,
)
from tests.e2e.support.people import PHONE
from tests.e2e.support.tables import NEW_SERIES

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Route

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

CANCEL = text(SOURCE_LANGUAGE, "table.nextSeriesCancel")


def test_a_sheet_left_open_while_the_next_series_is_dealt_stays_shut_at_the_end_of_the_series_after(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = PassedInTable(open_person, e2e_server, member_of, page_errors, PHONE)
    pass_the_series_in(table)
    first, second, third = table.pages[1], table.pages[2], table.pages[3]
    for person in (first, third):
        person.get_by_role("button", name=NEW_SERIES, exact=True).click()
    second.get_by_role("button", name=CHANGE, exact=True).click()
    expect(second.locator(NEXT_SHEET)).to_have_count(1)

    table.sessions[2].post(
        f"{table.api_path}{TABLE_NEW_SERIES_SUFFIX}",
        {"command_id": "second-new-series-0001", "series": 1, "settings": 0},
    )
    expect(second.locator(NEXT_SHEET)).to_have_count(0)
    pass_the_series_in(table)

    expect(second.get_by_role("button", name=CHANGE, exact=True)).to_be_visible()
    expect(second.locator(NEXT_SHEET)).to_have_count(0)
    assert page_errors == []


def test_a_sheet_open_while_another_seat_saves_says_the_settings_changed_and_shows_the_new_ones(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = PassedInTable(open_person, e2e_server, member_of, page_errors, PHONE)
    pass_the_series_in(table)
    first, second = table.pages[1], table.pages[2]
    sheet = second.locator(NEXT_SHEET)
    second.get_by_role("button", name=CHANGE, exact=True).click()
    expect(sheet.get_by_role("status")).to_have_count(0)
    first.get_by_role("button", name=CHANGE, exact=True).click()
    first.locator(NEXT_SHEET).get_by_role("button", name=MORE_GAMES).click()
    first.locator(NEXT_SHEET).get_by_role("button", name=SAVE, exact=True).click()

    expect(sheet.get_by_role("status")).to_have_text(text(SOURCE_LANGUAGE, "table.nextSeriesChanged"))
    expect(sheet.get_by_role("spinbutton")).to_have_attribute("aria-valuenow", str(SERIES_LENGTH + SERIES_LENGTH_STEP))
    sheet.get_by_role("button", name=SAVE, exact=True).click()
    expect(sheet).to_have_count(0)
    assert page_errors == []


def test_the_seat_that_saves_the_next_series_never_sees_its_own_sheet_say_the_settings_changed(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = PassedInTable(open_person, e2e_server, member_of, page_errors, PHONE)
    pass_the_series_in(table)
    first = table.pages[1]
    first.evaluate(
        """() => {
            window.seenStatus = [];
            new MutationObserver(() => {
                const status = document.querySelector('.sheet.next-series [role=status]');
                if (status) window.seenStatus.push(status.textContent);
            }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
        }""",
    )
    sheet = first.locator(NEXT_SHEET)
    longer = text(SOURCE_LANGUAGE, "table.seriesGames", count=SERIES_LENGTH + SERIES_LENGTH_STEP)
    held: list[Route] = []
    first.route(f"**{TABLES_PATH}/*{TABLE_NEXT_SETTINGS_SUFFIX}", lambda route: held.append(route))
    first.get_by_role("button", name=CHANGE, exact=True).click()
    sheet.get_by_role("button", name=MORE_GAMES).click()
    sheet.get_by_role("button", name=SAVE, exact=True).click()
    expect(sheet.get_by_role("button", name=SAVE, exact=True)).to_be_disabled()

    # The stream delivers the new revision while the save is still unanswered.
    answer = held[0].fetch()
    expect(first.locator(f"{NEXT_LINE} .chip.len")).to_have_text(longer)
    held[0].fulfill(response=answer)

    expect(sheet).to_have_count(0)
    for person in table.everyone:
        expect(person.locator(f"{NEXT_LINE} .chip.len")).to_have_text(longer)
    assert first.evaluate("window.seenStatus") == []
    assert page_errors == []


def test_the_next_series_sheet_closes_on_cancel_and_escape_stays_while_it_saves_and_tells_a_refused_save(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = PassedInTable(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    pass_the_series_in(table)
    second = table.pages[2]
    change = second.get_by_role("button", name=CHANGE, exact=True)
    sheet = second.locator(NEXT_SHEET)

    change.click()
    expect(sheet).to_have_count(1)
    second.keyboard.press("Escape")
    expect(sheet).to_have_count(0)

    change.click()
    sheet.get_by_role("button", name=CANCEL, exact=True).click()
    expect(sheet).to_have_count(0)

    held: list[Route] = []
    second.route(f"**{TABLES_PATH}/*{TABLE_NEXT_SETTINGS_SUFFIX}", lambda route: held.append(route))
    change.click()
    save = sheet.get_by_role("button", name=SAVE, exact=True)
    save.click()
    expect(save).to_be_disabled()
    second.keyboard.press("Escape")
    expect(sheet).to_have_count(1)

    refuse(held[0])
    expect(sheet.get_by_role("alert")).to_have_text(COMMAND_FAILED)
    expect(save).to_be_enabled()
    second.keyboard.press("Escape")
    expect(sheet).to_have_count(0)
    assert page_errors == []
