from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RamschTable
from tests.e2e.support.result_card import CARD, WON
from tests.e2e.support.server import AlwaysTheSameDeal, skat_on_new_database

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

DEAL_WHERE_ANNA_SWEEPS = 903
SWEEPER_SEAT = 1
DURCHMARSCH = text(SOURCE_LANGUAGE, "result.durchmarsch")
SERIES_LIST = text(SOURCE_LANGUAGE, "table.seriesList")


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, whose Ramsch played out card by smallest card gives Anna every trick."""
    with skat_on_new_database(tmp_path_factory, random_source=AlwaysTheSameDeal(DEAL_WHERE_ANNA_SWEEPS)) as server:
        yield server


def test_the_player_who_takes_every_trick_reads_won_and_the_others_read_durchmarsch(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()

    assert table.result()["durchmarsch_seat"] == SWEEPER_SEAT
    expect(table.pages[SWEEPER_SEAT].locator(CARD).get_by_role("heading")).to_have_text(WON)
    for person in (table.pages[2], table.pages[3], table.watcher):
        expect(person.locator(CARD).get_by_role("heading")).to_have_text(DURCHMARSCH)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_opened_durchmarsch_names_itself_on_an_end_line(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    person = table.pages[SWEEPER_SEAT]

    old_surface.series_count(person).click()
    games = person.get_by_role("dialog", name=SERIES_LIST)
    games.get_by_role("listitem").get_by_role("button").click()

    sheet = games.get_by_role("group", name=text(SOURCE_LANGUAGE, "table.sheetTitle", number="1"), exact=True)
    end_line = sheet.get_by_role("listitem").filter(has_text=text(SOURCE_LANGUAGE, "table.sheetDurchmarsch"))
    expect(end_line).to_have_count(1)
    assert page_errors == []
