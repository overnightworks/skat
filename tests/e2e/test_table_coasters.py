import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.tables import SIT_DOWN

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

PHONE_WIDTH_LIMIT = 900
COASTER = ".chair .coaster"
AWAY = ".chair .mark.away"
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
NEVER_UNDER_A_COASTER = (".plate", COASTER, ".mark", ".fan", ".plaque", ".result", ".actions")
PLAQUE_COVERS = (".fan", ".laid .face", ".chair .tile")
# The boxes are read in the browser in one pass, so a mark that leaves meanwhile is no stale handle that blocks a call.
OVERLAPS = """
    const overlaps = (first, second) =>
        first.x < second.x + second.width && second.x < first.x + first.width
        && first.y < second.y + second.height && second.y < first.y + first.height
    const boxOf = element => element.getClientRects().length ? element.getBoundingClientRect() : null
"""
# A coaster's tilt only widens the box the browser reports, so its own square is the centre and the unrotated side.
OFFENDERS_UNDER_A_COASTER = (
    "({coaster, others}) => {"
    + OVERLAPS
    + """
    const untilted = element => {
        const tilted = boxOf(element)
        if (tilted === null) return null
        const side = element.offsetWidth
        return {
            x: tilted.x + tilted.width / 2 - side / 2, y: tilted.y + tilted.height / 2 - side / 2,
            width: side, height: side,
        }
    }
    const offenders = []
    for (const own of document.querySelectorAll(coaster)) {
        const box = untilted(own)
        if (box === null) { offenders.push(coaster); continue }
        for (const selector of others) {
            for (const other of document.querySelectorAll(selector)) {
                if (other === own) continue
                const covered = selector === coaster ? untilted(other) : boxOf(other)
                if (covered !== null && overlaps(box, covered)) offenders.push(selector)
            }
        }
    }
    return offenders
}"""
)
OFFENDERS_OF_THE_TABLE_PAGE = (
    "({phone, covers}) => {"
    + OVERLAPS
    + """
    const offenders = []
    if (phone) {
        for (const selector of [".actions", "p.note"]) {
            for (const shown of document.querySelectorAll(selector)) {
                const box = boxOf(shown)
                if (box === null || box.y + box.height > window.innerHeight) offenders.push(selector)
            }
        }
    }
    for (const plaque of document.querySelectorAll(".plaque")) {
        const plaqueBox = boxOf(plaque)
        if (plaqueBox === null) { offenders.push(".plaque"); continue }
        for (const selector of covers) {
            for (const other of document.querySelectorAll(selector)) {
                const covered = boxOf(other)
                if (covered !== null && overlaps(plaqueBox, covered)) offenders.push(selector)
            }
        }
    }
    return offenders
}"""
)


@pytest.fixture
def play_a_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def play(form_factor: dict[str, Any]) -> PlayingTable:
        return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")

    return play


def expect_no_coaster(table: PlayingTable) -> None:
    for person in table.everyone:
        expect(person.locator(COASTER)).to_have_count(0)
    for seat in table.names:
        assert all(chair["total"] is None for chair in table.view(seat)["chairs"])


def expect_the_totals(table: PlayingTable, totals: dict[int, int]) -> None:
    """Every viewer reads each occupied chair's total as the answer counted it, and nothing on the page covers one."""
    for person in table.everyone:
        # A reloading player shows away to the others for a moment, which widens the plate under a coaster.
        expect(person.locator(AWAY)).to_have_count(0)
        expect(person.locator(COASTER)).to_have_count(len(totals))
        for seat, total in totals.items():
            sign = r"\D" if total < 0 else ""
            expect(person.locator(f".chair[data-seat='{seat}'] .coaster")).to_have_text(
                re.compile(rf"^{sign}{abs(total)}$")
            )
        expect_nothing_under_a_coaster(person)
        expect_the_table_page_clear(person)


def expect_the_table_page_clear(person: Page) -> None:
    """On a phone the bar and a note under it end inside the screen; the plaque lies over no fan, chair or laid card."""
    viewport = person.viewport_size
    assert viewport is not None
    phone = viewport["width"] < PHONE_WIDTH_LIMIT
    assert person.evaluate(OFFENDERS_OF_THE_TABLE_PAGE, {"phone": phone, "covers": PLAQUE_COVERS}) == []


def expect_nothing_under_a_coaster(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert person.evaluate(OFFENDERS_UNDER_A_COASTER, {"coaster": COASTER, "others": NEVER_UNDER_A_COASTER}) == []


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
        expect(person.locator(".result")).to_have_count(0)

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

    table.pages[leaver].locator(".actions").get_by_role("button", name=STAND_UP).click()
    expect(table.watcher.locator(f".chair[data-seat='{leaver}'] .coaster")).to_have_count(0)
    expect(table.watcher.locator(COASTER)).to_have_count(len(totals) - 1)
    table.watcher.locator(f".chair[data-seat='{leaver}']").get_by_role("button", name=SIT_DOWN).click()

    expect(table.watcher.locator(f".chair[data-seat='{leaver}'] .coaster")).to_have_text("0")
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_plates_and_marks_of_both_away_chairs_stay_clear_of_their_coasters(
    play_a_table: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = play_a_table(form_factor)
    table.play_out(CARDS_IN_A_GAME)
    away_seats = [seat for seat in table.names if seat != table.declarer_seat]
    onlooker = table.pages[table.declarer_seat]

    for seat in away_seats:
        table.pages[seat].close()

    expect(onlooker.locator(AWAY)).to_have_count(len(away_seats))
    expect(onlooker.locator(COASTER)).to_have_count(len(table.names))
    expect_nothing_under_a_coaster(onlooker)
    expect_the_table_page_clear(onlooker)
