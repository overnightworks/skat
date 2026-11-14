import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import PlayingTable
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RamschTable

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

GAME_SHEET = ".game-list .game-sheet"
SHEET_ROUTE = f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}/*"
LIST_ROUTE = f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}"
LONG_LABEL_LEVELS = ["hand", "schneider", "schneider_announced", "schwarz", "schwarz_announced", "ouvert"]
PUT_AWAY_FROM_THE_HAND = 2
DEALT_CARDS = 30
SEATS = 3
SERVER_ERROR = 500


def open_the_game(person: Page) -> None:
    person.locator(".series-count").click()
    person.locator(".game-list .grow").click()


def without_cards(route: Route) -> None:
    sheet = route.fetch().json()
    sheet["cards"] = None
    route.fulfill(json=sheet)


def with_the_skat_laid(route: Route) -> None:
    sheet = route.fetch().json()
    sheet["cards"]["laid_skat"] = sheet["cards"]["skat"]
    route.fulfill(json=sheet)


def as_the_list_names_it(fields: dict[str, object]) -> Callable[[Route], None]:
    def named(route: Route) -> None:
        answer = route.fetch().json()
        for entry in answer["entries"]:
            entry.update(fields)
        route.fulfill(json=answer)

    return named


def broken(route: Route) -> None:
    route.fulfill(status=SERVER_ERROR, content_type="application/json", body=json.dumps({}))


def a_declared_game_with_two_hand_cards_put_away(
    open_person: Callable[..., Page],
    server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> PlayingTable:
    """The declarer picks the skat up and puts away two cards of the hand he was dealt, then the forehand leads."""
    declaring = DeclaringTable(open_person, server, member_of, page_errors, form_factor)
    declaring.declare_through_the_api(action="take")
    view = json.loads(declaring.sessions[declaring.declarer_seat].get(declaring.api_path))
    skat = declaring.skat()
    dealt = sorted((card["suit"], card["rank"]) for card in view["hand"]["own_cards"])
    own = [card for card in dealt if card not in skat][:PUT_AWAY_FROM_THE_HAND]
    declaring.declare_through_the_api(action="put_back", cards=[{"suit": suit, "rank": rank} for suit, rank in own])
    declaring.declare_through_the_api(action="declare", game="kreuz", hand=False, ouvert=False, announcement="none")
    return PlayingTable(declaring, None)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_declared_game_given_up_in_its_first_trick_shows_its_count_its_cards_and_the_trick_it_left(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = a_declared_game_with_two_hand_cards_put_away(open_person, e2e_server, member_of, page_errors, form_factor)
    table.play_out(1)
    table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
    person = table.pages[table.declarer_seat]

    open_the_game(person)

    expect(person.locator(f"{GAME_SHEET} .points")).to_be_visible()
    expect(person.locator(f"{GAME_SHEET} .sheet-head .dot")).to_have_class(
        re.compile(rf"\bseat-{table.declarer_seat}\b")
    )
    assert person.locator(f"{GAME_SHEET} .points .side").evaluate_all(
        "sides => sides.every(side => side.scrollWidth <= side.clientWidth)"
    )
    expect(person.locator(f"{GAME_SHEET} .hc.put-away")).to_have_count(PUT_AWAY_FROM_THE_HAND)
    expect(person.locator(f"{GAME_SHEET} .hc.unplayed")).to_have_count(DEALT_CARDS - PUT_AWAY_FROM_THE_HAND - 1)
    trick = person.locator(f"{GAME_SHEET} .tricks .trick-row:not(.ended)")
    expect(trick).to_have_count(1)
    expect(trick.locator(".trick-card")).to_have_count(1)
    expect(trick.locator(".pts")).to_have_count(0)
    expect(person.locator(f"{GAME_SHEET} .trick-row.ended")).to_contain_text(text(SOURCE_LANGUAGE, "result.givenUp"))
    assert page_errors == []


def test_a_null_games_sheet_draws_no_points_bar_and_still_its_tricks(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = a_declared_game_with_two_hand_cards_put_away(open_person, e2e_server, member_of, page_errors, PHONE)
    table.play_out(1)
    table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
    person = table.pages[table.declarer_seat]
    person.route(LIST_ROUTE, as_the_list_names_it({"game": "null"}))

    open_the_game(person)

    expect(person.locator(f"{GAME_SHEET} .tricks .trick-row:not(.ended)")).to_have_count(1)
    expect(person.locator(f"{GAME_SHEET} .points")).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_long_game_label_wraps_in_the_sheet_head_instead_of_being_cut(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = a_declared_game_with_two_hand_cards_put_away(open_person, e2e_server, member_of, page_errors, form_factor)
    table.play_out(1)
    table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
    person = table.pages[table.declarer_seat]
    person.route(LIST_ROUTE, as_the_list_names_it({"levels": LONG_LABEL_LEVELS, "hand": True, "ouvert": True}))

    open_the_game(person)

    for part in (".sheet-head b", ".sheet-head small"):
        assert person.locator(f"{GAME_SHEET} {part}").evaluate("label => label.scrollWidth <= label.clientWidth")
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_ramsch_sheet_draws_every_dot_round_and_its_tricks_inside_the_panel(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    person = table.pages[1]

    open_the_game(person)

    expect(person.locator(f"{GAME_SHEET} .seat-eyes > span .dot")).to_have_count(3)
    sizes = person.locator(f"{GAME_SHEET} .dot").evaluate_all(
        "dots => dots.map(dot => { const box = dot.getBoundingClientRect(); return [box.width, box.height]; })"
    )
    assert all(abs(width - height) < 1 for width, height in sizes)
    seat_dots = person.locator(f"{GAME_SHEET} .seat-eyes .dot")
    assert len(set(seat_dots.evaluate_all("dots => dots.map(dot => getComputedStyle(dot).backgroundImage)"))) == SEATS
    loser = person.locator(f"{GAME_SHEET} .seat-eyes > .most .dot").first
    loser_seat = loser.evaluate("dot => [...dot.classList].find(name => name.startsWith('seat-'))")
    expect(person.locator(f"{GAME_SHEET} .sheet-head .dot")).to_have_class(re.compile(rf"\b{loser_seat}\b"))
    assert person.locator(f"{GAME_SHEET} .tricks").evaluate(
        "tricks => tricks.getBoundingClientRect().right <= tricks.closest('.game-list').getBoundingClientRect().right"
    )
    assert page_errors == []


def test_a_ramsch_sheet_with_a_laid_skat_puts_the_taker_dot_beside_the_laid_skat_only(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()
    person = table.pages[1]
    person.route(SHEET_ROUTE, with_the_skat_laid)

    open_the_game(person)

    pairs = person.locator(f"{GAME_SHEET} .skatline .pair")
    laid = pairs.filter(has_text=text(SOURCE_LANGUAGE, "table.sheetSkatLaid"))
    expect(laid).to_have_count(1)
    expect(laid.locator(".dot")).not_to_have_count(0)
    expect(pairs.locator(".dot")).to_have_count(laid.locator(".dot").count())
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_game_the_server_kept_no_cards_of_says_so_and_still_counts(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    person = table.pages[1]
    person.route(SHEET_ROUTE, without_cards)

    open_the_game(person)

    expect(person.locator(f"{GAME_SHEET} .empty")).to_have_text(text(SOURCE_LANGUAGE, "table.sheetNoCards"))
    expect(person.locator(f"{GAME_SHEET} .seat-eyes > span")).to_have_count(3)
    assert page_errors == []


def test_a_game_the_server_cannot_read_says_so(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    # The browser logs the failed read as a console error; that failure is the point of this test.
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    table.pass_all()
    table.play_out()
    person = table.pages[1]
    person.route(SHEET_ROUTE, broken)

    open_the_game(person)

    expect(person.locator(f"{GAME_SHEET} [role=alert]")).to_have_text(text(SOURCE_LANGUAGE, "table.sheetFailed"))
    assert page_errors == []
