import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import CARD as RESULT_CARD
from tests.e2e.support.table_menu import menu_button
from tests.e2e.support.tables import chair_of, sit_in

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
# A coaster is a key named by its word and the total it shows.
COASTER = re.compile(rf"^{re.escape(text(SOURCE_LANGUAGE, 'table.objectCoaster'))} ")


def coasters(scope: Page | Locator) -> Locator:
    return scope.get_by_role("button", name=COASTER)


@pytest.fixture
def play_a_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    # its own settings: this file's constants differ from the other file's, whose closure reads the same
    def play(form_factor: dict[str, Any]) -> PlayingTable:
        return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")

    return play


def expect_no_coaster(table: PlayingTable) -> None:
    for person in table.everyone:
        expect(coasters(person)).to_have_count(0)
    for seat in table.names:
        assert all(chair["total"] is None for chair in table.view(seat)["chairs"])


def expect_the_totals(table: PlayingTable, totals: dict[int, int]) -> None:
    """Every viewer reads each occupied chair's total as the answer counted it."""
    for person in table.everyone:
        expect(coasters(person)).to_have_count(len(totals))
        for seat, total in totals.items():
            sign = r"\D" if total < 0 else ""
            expect(coasters(chair_of(person, seat))).to_have_text(re.compile(rf"^{sign}{abs(total)}$"))


def totals_of(table: PlayingTable) -> dict[int, int]:
    return {chair["seat"]: chair["total"] for chair in table.view(table.declarer_seat)["chairs"]}


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_no_coaster_before_the_first_result_then_every_chair_shows_its_persons_total(
    play_a_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = play_a_table(form_factor)
    expect_no_coaster(table)

    table.play_out(CARDS_IN_A_GAME)

    gains = {gain["seat"]: gain["gain"] for gain in table.result()["gains"]}
    expect_the_totals(table, gains)
    assert totals_of(table) == gains
    for person in table.everyone:
        person.reload()
    expect_the_totals(table, gains)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_coasters_stay_in_the_next_hand(
    play_a_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = play_a_table(form_factor)
    table.play_out(CARDS_IN_A_GAME)
    totals = totals_of(table)
    for seat in table.names:
        table.ready_through_the_api(seat)
    for person in table.everyone:
        expect(person.locator(RESULT_CARD)).to_have_count(0)

    expect_the_totals(table, totals)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_freed_chair_has_no_coaster_and_a_newcomer_on_it_reads_zero(
    play_a_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = play_a_table(form_factor)
    table.play_out(CARDS_IN_A_GAME)
    totals = totals_of(table)
    leaver = next(seat for seat in table.names if seat != table.declarer_seat)

    menu_button(table.pages[leaver], STAND_UP).click()
    expect(coasters(chair_of(table.watcher, leaver))).to_have_count(0)
    expect(coasters(table.watcher)).to_have_count(len(totals) - 1)
    sit_in(table.watcher, leaver)

    expect(coasters(chair_of(table.watcher, leaver))).to_have_text("0")
    assert page_errors == []
