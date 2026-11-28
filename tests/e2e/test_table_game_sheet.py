import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import PlayingTable
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RamschTable

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SHEET_ROUTE = f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}/*"
LIST_ROUTE = f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}"
PUT_AWAY_FROM_THE_HAND = 2
DEALT_CARDS = 30
SERVER_ERROR = 500
SERIES_LIST = text(SOURCE_LANGUAGE, "table.seriesList")
TRICK_POINTS = text(SOURCE_LANGUAGE, "result.trickPoints")
FIRST_TRICK = text(SOURCE_LANGUAGE, "table.sheetTrick", number="1")
CARD_PUT_AWAY = text(SOURCE_LANGUAGE, "table.sheetCardPutAway")
CARD_UNPLAYED = text(SOURCE_LANGUAGE, "table.sheetCardUnplayed")


def open_the_game(person: Page) -> Locator:
    """The sheet of the series' first game, opened from the count and the list's one row."""
    old_surface.series_count(person).click()
    games = person.get_by_role("dialog", name=SERIES_LIST)
    games.get_by_role("listitem").get_by_role("button").click()
    return games.get_by_role("group", name=text(SOURCE_LANGUAGE, "table.sheetTitle", number="1"), exact=True)


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

    sheet = open_the_game(person)

    expect(sheet.get_by_role("group", name=TRICK_POINTS)).to_be_visible()
    expect(sheet.get_by_title(CARD_PUT_AWAY, exact=True)).to_have_count(PUT_AWAY_FROM_THE_HAND)
    expect(sheet.get_by_title(CARD_UNPLAYED, exact=True)).to_have_count(DEALT_CARDS - PUT_AWAY_FROM_THE_HAND - 1)
    trick = sheet.get_by_role("listitem", name=FIRST_TRICK, exact=True)
    # The trick it left holds the one card led, named by who led it, and neither a taker nor a count.
    leader = table.names[table.seat_at["forehand"]]
    expect(trick.get_by_role("img")).to_have_count(1)
    expect(trick.get_by_role("img", name=leader, exact=True)).to_have_count(1)
    expect(trick).to_have_text(re.compile(r"^\D*1\D*$"))
    expect(sheet.get_by_role("listitem")).to_have_count(2)
    expect(sheet.get_by_role("listitem").last).to_contain_text(text(SOURCE_LANGUAGE, "result.givenUp"))
    assert page_errors == []


def test_a_null_games_sheet_shows_no_trick_points_and_still_its_tricks(
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

    sheet = open_the_game(person)

    expect(sheet.get_by_role("listitem", name=FIRST_TRICK, exact=True)).to_have_count(1)
    expect(sheet.get_by_role("group", name=TRICK_POINTS)).to_have_count(0)
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

    sheet = open_the_game(person)

    pairs = sheet.locator(".skatline .pair")
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

    sheet = open_the_game(person)

    expect(sheet.get_by_text(text(SOURCE_LANGUAGE, "table.sheetNoCards"), exact=True)).to_be_visible()
    # The sheet still counts: each seat stands on it once, beside its eyes.
    for name in table.names.values():
        expect(sheet.get_by_role("img", name=name, exact=True)).to_have_count(1)
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

    sheet = open_the_game(person)

    expect(sheet.get_by_role("alert")).to_have_text(text(SOURCE_LANGUAGE, "table.sheetFailed"))
    assert page_errors == []
