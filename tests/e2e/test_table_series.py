import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.table.records import SERIES_LENGTH_STEP
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.passed_in_series import (
    CHANGE,
    COMMAND_FAILED,
    COUNT,
    MORE_GAMES,
    NEXT_LINE,
    NEXT_SHEET,
    SAVE,
    SERIES_LENGTH,
    PassedInTable,
    game_count,
    refuse,
)
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RamschTable
from tests.e2e.support.result_card import MINUS, WAITING_FOR_PLAYERS, waiting_for
from tests.e2e.support.table_menu import close_table_menu, menu_button
from tests.e2e.support.tables import NEW_SERIES, chair_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Route

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

TRICKS_IN_A_GAME = 10
PLAYS_IN_A_TRICK = 3
SEATS = 3
PUT_AWAY_PER_SEAT = 2
SERIES_LIST = text(SOURCE_LANGUAGE, "table.seriesList")
SHEET_BACK = text(SOURCE_LANGUAGE, "table.sheetBack")
SHEET_SKAT = text(SOURCE_LANGUAGE, "table.sheetSkat")
STANDING = ".result.standing"
SERIES_ENDED = text(SOURCE_LANGUAGE, "table.seriesEnded")
END_SERIES = text(SOURCE_LANGUAGE, "table.endSeries")
END_SERIES_SURE = text(SOURCE_LANGUAGE, "table.endSeriesSure")
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
STOP_PLAYING = text(SOURCE_LANGUAGE, "table.stopPlaying")
RULE_SETS = text(SOURCE_LANGUAGE, "start.ruleSets")
SAVE_RULES = text(SOURCE_LANGUAGE, "start.saveRules")
RULE_KONTRA = text(SOURCE_LANGUAGE, "start.ruleKontra")
RULE_RAMSCH = text(SOURCE_LANGUAGE, "start.ruleRamsch")
RAMSCH = text(SOURCE_LANGUAGE, "game.ramsch")
YES = text(SOURCE_LANGUAGE, "table.yes")
NO = text(SOURCE_LANGUAGE, "table.no")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
GONE = text(SOURCE_LANGUAGE, "table.seriesGone")
TAPPED_WEITER = text(SOURCE_LANGUAGE, "table.readyMark")
SAID_NO = text(SOURCE_LANGUAGE, "table.saidNo")
COASTER = text(SOURCE_LANGUAGE, "table.objectCoaster")
# A point of the room outside the centred panel, where a tap lands on the backdrop of the list.
BESIDE_THE_PANEL = (4, 4)


# Stands in a sentence for the value the page fills in.
GAP = "\n"


def with_anything_in_its_gap(sentence: str) -> re.Pattern[str]:
    """The sentence with anything in the place of its `GAP`."""
    before, after = sentence.split(GAP)
    return re.compile(re.escape(before) + ".+" + re.escape(after))


# The line that counts down the minute a seat has to answer „Neue Serie“ in.
ANSWER_CLOCK = with_anything_in_its_gap(text(SOURCE_LANGUAGE, "table.answerClockEnds", time=GAP))
# The line that counts down the time an asked seat has to answer a request in.
ANSWER_BY = with_anything_in_its_gap(text(SOURCE_LANGUAGE, "table.answerClock", time=GAP))
# The line that tells whose given „Neue Serie“ a save takes back.
TAKES_BACK = with_anything_in_its_gap(text(SOURCE_LANGUAGE, "table.nextSeriesTakeBack", names=GAP))
TRICK = with_anything_in_its_gap(text(SOURCE_LANGUAGE, "table.sheetTrick", number=GAP))
PUT_BY = with_anything_in_its_gap(text(SOURCE_LANGUAGE, "table.sheetPutBy", name=GAP))


def shown(total: int) -> str:
    return f"{MINUS}{-total}" if total < 0 else str(total)


def answer_the_ask(person: Page, word: str) -> None:
    old_surface.requests(person).get_by_role("button", name=word, exact=True).click()


def game_list(person: Page) -> Locator:
    return person.get_by_role("dialog", name=SERIES_LIST)


def listed_games(person: Page) -> Locator:
    return game_list(person).get_by_role("listitem").get_by_role("button")


def open_the_first_game(person: Page) -> Locator:
    """The sheet of the series' first game, opened from the count and the list's one row."""
    person.locator(COUNT).click()
    listed_games(person).click()
    title = text(SOURCE_LANGUAGE, "table.sheetTitle", number="1")
    return game_list(person).get_by_role("group", name=title, exact=True)


def ready_mark(person: Page, seat: int) -> Locator:
    return chair_of(person, seat).get_by_title(TAPPED_WEITER, exact=True)


def standings_heading(person: Page) -> Locator:
    return person.get_by_role("heading", name=SERIES_ENDED, exact=True)


def weiter_key(person: Page) -> Locator:
    return person.get_by_role("button", name=WEITER, exact=True)


def new_series_key(person: Page) -> Locator:
    return person.get_by_role("button", name=NEW_SERIES, exact=True)


def propose_the_end(person: Page) -> None:
    """The menu's key asks a second tap, as the other armed keys do."""
    menu_button(person, END_SERIES).click()
    menu_button(person, END_SERIES_SURE).click()


def expect_the_end_behind_the_menu_key_and_weiter_beside_it(person: Page) -> None:
    expect(menu_button(person, END_SERIES)).to_be_visible()
    close_table_menu(person)
    expect(person.get_by_role("button", name=END_SERIES, exact=True)).to_have_count(0)
    expect(person.get_by_role("button", name=STAND_UP, exact=True)).to_have_count(0)
    expect(weiter_key(person)).to_be_visible()


def expect_the_proposal_asked(table: RamschTable) -> None:
    """The first seat proposed: the other two are asked, the proposer waits for them and the watcher only reads."""
    proposed = text(SOURCE_LANGUAGE, "table.wantsToEndSeries", name=table.names[1])
    for person in (table.pages[2], table.pages[3], table.watcher):
        expect(old_surface.requests(person)).to_contain_text(proposed)
    expect(old_surface.requests(table.pages[1])).to_contain_text(waiting_for([table.names[2], table.names[3]]))
    expect(old_surface.requests(table.watcher).get_by_role("button")).to_have_count(0)
    for person in (table.pages[1], table.pages[2], table.pages[3]):
        expect(weiter_key(person)).to_have_count(0)


def expect_the_standings(person: Page, standings: list[dict[str, Any]], own_name: str | None) -> None:
    expect(standings_heading(person)).to_have_count(1)
    expect(old_surface.requests(person)).to_have_count(0)
    expect(person.locator(COUNT)).to_have_count(0)
    expect(weiter_key(person)).to_have_count(0)
    rows = person.locator(f"{STANDING} .rank")
    expect(rows).to_have_count(len(standings))
    for index, standing in enumerate(standings):
        row = rows.nth(index)
        expect(row.locator(".place")).to_have_text(str(standing["place"]))
        name = YOU if standing["display_name"] == own_name else standing["display_name"]
        expect(row.locator("b")).to_have_text(name)
        expect(row.locator("small")).to_have_count(0)
        expect(row.locator(".sum")).to_have_text(shown(standing["total"]))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_list_of_the_first_game_says_nothing_is_finished(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    first = table.pages[1]
    first.locator(COUNT).click()
    nothing_finished = text(SOURCE_LANGUAGE, "table.seriesListEmpty")
    expect(game_list(first).get_by_text(nothing_finished, exact=True)).to_be_visible()
    first.keyboard.press("Escape")
    expect(game_list(first)).not_to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_mark_counts_the_game_and_the_list_names_the_newest_game_first(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(game_count(1))

    table.pass_all()
    table.play_out()
    table.ready_all()

    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(game_count(2))
    table.pass_all()
    table.play_out()
    for person in table.everyone:
        person.locator(COUNT).click()
        # A row opens with the number of its game.
        expect(listed_games(person)).to_have_text([re.compile(r"^\s*2\D"), re.compile(r"^\s*1\D")])
        expect(listed_games(person).first).to_contain_text(RAMSCH)
        person.keyboard.press("Escape")
        expect(game_list(person)).not_to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_game_of_the_list_opens_with_every_seat_and_every_trick_and_the_way_back_returns_to_the_list(
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
    sheet = open_the_first_game(person)

    for name in table.names.values():
        expect(sheet.get_by_role("img", name=name, exact=True)).not_to_have_count(0)
    tricks = sheet.get_by_role("listitem", name=TRICK)
    expect(tricks).to_have_count(TRICKS_IN_A_GAME)
    # Every card of a trick names the seat that played it, and every trick the seat that took it.
    expect(tricks.get_by_role("img")).to_have_count(TRICKS_IN_A_GAME * (PLAYS_IN_A_TRICK + 1))

    person.get_by_role("button", name=SHEET_BACK).click()
    expect(sheet).to_have_count(0)
    expect(listed_games(person)).to_have_count(1)
    person.keyboard.press("Escape")
    expect(game_list(person)).not_to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_game_with_three_putters_names_every_putter_beside_the_skat(
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

    def three_putters(route: Route) -> None:
        sheet = route.fetch().json()
        dealt = [dealt["card"] for hand in sheet["cards"]["hands"] for dealt in hand["cards"]]
        sheet["cards"]["put_away"] = [
            {"seat": seat, "card": dealt[PUT_AWAY_PER_SEAT * (seat - 1) + each]}
            for seat in range(1, SEATS + 1)
            for each in range(PUT_AWAY_PER_SEAT)
        ]
        route.fulfill(json=sheet)

    person.route(f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}/*", three_putters)
    sheet = open_the_first_game(person)

    expect(sheet.get_by_text(SHEET_SKAT, exact=True)).to_be_visible()
    expect(sheet.get_by_role("img", name=PUT_BY)).to_have_count(SEATS)
    for name in table.names.values():
        put_by = text(SOURCE_LANGUAGE, "table.sheetPutBy", name=name)
        expect(sheet.get_by_role("img", name=put_by, exact=True)).to_have_count(1)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_passed_in_hand_counts_and_a_passed_in_last_game_ends_the_series_with_neue_serie_and_no_weiter(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = PassedInTable(open_person, e2e_server, member_of, page_errors, form_factor)
    for game in (1, 2):
        for person in table.everyone:
            expect(person.locator(COUNT)).to_have_text(game_count(game))
        table.pass_all()
    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(game_count(3))
    table.pass_all()

    for person in table.pages.values():
        expect(new_series_key(person)).to_be_visible()
        expect(weiter_key(person)).to_have_count(0)
    for person in table.everyone:
        expect(standings_heading(person)).to_have_count(1)
        expect(person.locator(COUNT)).to_have_count(0)
        expect(person.locator(NEXT_LINE)).to_contain_text(text(SOURCE_LANGUAGE, "rules.chipOfficial"))
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_early_end_is_proposed_answered_and_ends_in_the_standings_until_all_three_tap_neue_serie(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    first, second, third = table.pages[1], table.pages[2], table.pages[3]

    expect_the_end_behind_the_menu_key_and_weiter_beside_it(first)
    propose_the_end(first)
    expect_the_proposal_asked(table)

    answer_the_ask(second, YES)
    expect(old_surface.requests(second)).to_contain_text(waiting_for([table.names[3]]))
    answer_the_ask(third, YES)

    # The last tap returns before the stream brings the end, so the view is read once every page shows the standings.
    for person in table.everyone:
        expect(standings_heading(person)).to_have_count(1)
    series = table.view(1)["series"]
    assert series["over"] is True
    for seat, person in table.pages.items():
        expect_the_standings(person, series["standings"], table.names[seat])
    expect_the_standings(table.watcher, series["standings"], None)
    watching = text(SOURCE_LANGUAGE, "table.watchingOnly")
    expect(table.watcher.get_by_text(watching)).to_be_visible()
    expect(new_series_key(table.watcher)).to_have_count(0)

    new_series_key(first).click()
    new_series_key(second).click()
    for person in table.everyone:
        expect(ready_mark(person, 1)).to_have_count(1)
        expect(ready_mark(person, 2)).to_have_count(1)
        expect(standings_heading(person)).to_have_count(1)
    expect(first.get_by_text(waiting_for([table.names[3]]), exact=True)).to_be_visible()

    new_series_key(third).click()
    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(game_count(1))
        expect(standings_heading(person)).to_have_count(0)
        expect(old_surface.chairs(person).get_by_role("button", name=f"{COASTER} 0", exact=True)).to_have_count(SEATS)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_series_end_offers_exactly_neue_serie_and_aufhoeren_and_aufhoeren_sends_every_page_to_the_lobby(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    first, second, third = table.pages[1], table.pages[2], table.pages[3]
    propose_the_end(first)
    answer_the_ask(second, YES)
    answer_the_ask(third, YES)
    for person in table.everyone:
        expect(standings_heading(person)).to_have_count(1)
        expect(person.locator(NEXT_LINE)).to_have_count(1)
        expect(person.get_by_text(ANSWER_CLOCK)).to_have_count(0)
    for person in table.pages.values():
        expect(person.locator(old_surface.ACTIONS).get_by_role("button")).to_have_text([NEW_SERIES, STOP_PLAYING])
    expect(table.watcher.locator(old_surface.ACTIONS).get_by_role("button")).to_have_count(0)

    new_series_key(first).click()
    for person in table.everyone:
        expect(person.get_by_text(ANSWER_CLOCK)).to_have_count(1)
        expect(ready_mark(person, 1)).to_have_count(1)

    second.get_by_role("button", name=STOP_PLAYING, exact=True).click()
    lobby = re.compile(rf"^{re.escape(e2e_server.base_url)}/?$")
    for person in table.everyone:
        expect(person).to_have_url(lobby)
    link = f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{table.api_path.removeprefix(TABLES_PATH + '/')}"
    # The browser coverage collector aborts a Playwright navigation away from the lobby; a page's own one goes through.
    table.watcher.evaluate("address => location.assign(address)", link)
    expect(table.watcher.get_by_role("heading", name=text(SOURCE_LANGUAGE, "closed.seriesEnded"))).to_be_visible()
    expect(table.watcher).to_have_url(link)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_seated_member_changes_the_next_series_and_the_save_takes_back_every_neue_serie(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    first, second, third = table.pages[1], table.pages[2], table.pages[3]
    propose_the_end(first)
    answer_the_ask(second, YES)
    answer_the_ask(third, YES)
    for person in table.everyone:
        expect(person.locator(NEXT_LINE)).to_have_count(1)
    expect(table.watcher.get_by_role("button", name=CHANGE, exact=True)).to_have_count(0)
    new_series_key(first).click()
    for person in table.everyone:
        expect(person.get_by_text(ANSWER_CLOCK)).to_have_count(1)

    second.get_by_role("button", name=CHANGE, exact=True).click()
    sheet = second.locator(NEXT_SHEET)
    expect(sheet).to_be_visible()
    expect(sheet.get_by_role("spinbutton")).to_have_attribute("aria-valuenow", str(SERIES_LENGTH))
    expect(sheet.get_by_text(TAKES_BACK)).to_be_visible()
    expect(sheet.get_by_text(ANSWER_CLOCK)).to_be_visible()
    expect(sheet.get_by_role("radiogroup", name=RULE_SETS).get_by_role("radio", checked=True)).to_have_count(0)
    expect(sheet.get_by_role("switch", name=RULE_RAMSCH, exact=True)).to_have_attribute("aria-checked", "true")
    expect(sheet.get_by_role("switch", name=RULE_KONTRA, exact=True)).to_have_attribute("aria-checked", "false")
    expect(sheet.get_by_role("group", name=SAVE_RULES)).to_have_count(0)
    sheet.get_by_role("switch", name=RULE_KONTRA, exact=True).click()
    expect(sheet.get_by_role("group", name=SAVE_RULES)).to_have_count(1)
    sheet.get_by_role("button", name=MORE_GAMES).click()
    sheet.get_by_role("button", name=SAVE, exact=True).click()

    longer = text(SOURCE_LANGUAGE, "table.seriesGames", count=SERIES_LENGTH + SERIES_LENGTH_STEP)
    for person in table.everyone:
        expect(person.locator(NEXT_LINE)).to_contain_text(longer)
        expect(old_surface.chairs(person).get_by_title(TAPPED_WEITER, exact=True)).to_have_count(0)
        expect(person.get_by_text(ANSWER_CLOCK)).to_have_count(0)
    expect(second.locator(NEXT_SHEET)).to_have_count(0)

    for person in table.pages.values():
        new_series_key(person).click()
    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(
            text(SOURCE_LANGUAGE, "table.seriesCount", game="1", count=SERIES_LENGTH + SERIES_LENGTH_STEP),
        )
    assert page_errors == []


def test_a_no_ends_the_proposal_names_its_refuser_at_the_chair_and_offers_no_new_proposal(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()
    first, second = table.pages[1], table.pages[2]
    propose_the_end(first)
    expect_the_proposal_asked(table)

    answer_the_ask(second, NO)

    for person in table.everyone:
        expect(old_surface.requests(person)).to_have_count(0)
        expect(chair_of(person, 2).get_by_title(SAID_NO, exact=True)).to_have_count(1)
        expect(person.locator(old_surface.SEAT_NOTICE)).to_be_visible()
    expect(weiter_key(first)).to_be_visible()
    expect(menu_button(first, END_SERIES)).to_have_count(0)
    assert page_errors == []


def test_a_list_the_server_cannot_read_says_so_and_a_tap_beside_the_panel_closes_it(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    # The browser logs the refused read as a console error; that refusal is the point of this test.
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    first = table.pages[1]
    first.route(f"**{TABLES_PATH}/*{TABLE_LIST_SUFFIX}", refuse)

    first.locator(COUNT).click()

    expect(game_list(first).get_by_role("alert")).to_have_text(text(SOURCE_LANGUAGE, "table.seriesListFailed"))
    first.mouse.click(*BESIDE_THE_PANEL)
    expect(game_list(first)).not_to_be_visible()
    assert page_errors == []


def test_a_proposed_end_the_server_refuses_shows_the_failure_and_leaves_the_key_to_tap_again(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    # The browser logs the refused proposal as a console error; that refusal is the point of this test.
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    table.pass_all()
    table.play_out()
    first = table.pages[1]
    first.route(f"**{TABLES_PATH}/*{TABLE_SERIES_END_AGREE_SUFFIX}", refuse)

    propose_the_end(first)

    expect(old_surface.note(first)).to_have_text(COMMAND_FAILED)
    expect(menu_button(first, END_SERIES)).to_be_enabled()
    for person in (table.pages[2], table.pages[3]):
        expect(old_surface.requests(person)).to_have_count(0)
    assert page_errors == []


def test_a_player_who_stands_up_from_the_ended_series_stays_in_the_standings_marked_as_gone(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()
    propose_the_end(table.pages[1])
    answer_the_ask(table.pages[2], YES)
    answer_the_ask(table.pages[3], YES)
    for person in table.everyone:
        expect(standings_heading(person)).to_have_count(1)

    menu_button(table.pages[3], STAND_UP).click()

    for person in table.everyone:
        leaver = old_surface.result_card(person).get_by_role("listitem").filter(has_text=table.names[3])
        expect(leaver).to_contain_text(GONE)
    assert page_errors == []


def test_a_neue_serie_stays_given_and_waits_for_players_when_the_last_silent_seat_stands_up(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()
    propose_the_end(table.pages[1])
    answer_the_ask(table.pages[2], YES)
    answer_the_ask(table.pages[3], YES)
    first, second, third = table.pages[1], table.pages[2], table.pages[3]
    for person in (first, second):
        new_series_key(person).click()
    expect(first.get_by_text(ANSWER_CLOCK)).to_have_count(1)

    menu_button(third, STAND_UP).click()

    for person in (first, second):
        expect(person.get_by_text(ANSWER_CLOCK)).to_have_count(0)
        expect(person.get_by_text(WAITING_FOR_PLAYERS, exact=True)).to_be_visible()
        expect(new_series_key(person)).to_have_count(0)
    for seat in (1, 2):
        expect(ready_mark(first, seat)).to_have_count(1)
    assert page_errors == []


def test_a_proposal_whose_asked_players_stood_up_opens_and_waits_for_players(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()
    proposer = table.pages[1]
    propose_the_end(proposer)
    expect_the_proposal_asked(table)

    for leaver in (table.pages[2], table.pages[3]):
        menu_button(leaver, STAND_UP).click()
    proposer.reload()

    # The request names nobody it waits for: beside the wait for players it holds only the time left to answer.
    expect(old_surface.requests(proposer)).to_have_text(
        re.compile(rf"^\s*{re.escape(WAITING_FOR_PLAYERS)}\s*{ANSWER_BY.pattern}\s*$")
    )
    assert page_errors == []
