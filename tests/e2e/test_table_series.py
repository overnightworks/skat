import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.table.records import SERIES_LENGTH_STEP
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
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
from tests.e2e.support.result_card import MINUS, waiting_for
from tests.e2e.support.table_menu import close_table_menu, menu_button, open_table_menu

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Route

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

# A room this short cannot show two rows of the list beside its heading.
SHORT_ROOM = 160
# A room that holds the head of an opened game and leaves its tricks less height than they need.
SHEET_ROOM = 480
GAME_LIST = ".game-list"
ROWS = f"{GAME_LIST} .grow"
SHEET = f"{GAME_LIST} .game-sheet"
TRICKS = f"{SHEET} .tricks"
# The list of tricks closes with a row for how the game ended, which holds no cards.
PLAYED_TRICKS = f"{TRICKS} .trick-row:not(.ended)"
TRICKS_IN_A_GAME = 10
PLAYS_IN_A_TRICK = 3
SEATS = 3
PUT_AWAY_PER_SEAT = 2
# The panel body pads its content by less than this on each side.
FRAME_PADDING = 24
SHEET_BACK = text(SOURCE_LANGUAGE, "table.sheetBack")
STANDING = ".result.standing"
ASK = ".plaque.ask"
REFUSAL_LINE = ".notice.seat"
COASTER = ".coaster"
END_KEY = ".row.end-series"
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
NEW_SERIES = text(SOURCE_LANGUAGE, "table.newSeries")
STOP_PLAYING = text(SOURCE_LANGUAGE, "table.stopPlaying")
RULE_SETS = text(SOURCE_LANGUAGE, "start.ruleSets")
SAVE_RULES = text(SOURCE_LANGUAGE, "start.saveRules")
RULE_KONTRA = text(SOURCE_LANGUAGE, "start.ruleKontra")
RULE_RAMSCH = text(SOURCE_LANGUAGE, "start.ruleRamsch")
ANSWER_CLOCK = ".stage > .plaque.timer"
RAMSCH = text(SOURCE_LANGUAGE, "game.ramsch")
YES = text(SOURCE_LANGUAGE, "table.yes")
NO = text(SOURCE_LANGUAGE, "table.no")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
GONE = text(SOURCE_LANGUAGE, "table.seriesGone")
# A point of the room outside the centred panel, where a tap lands on the backdrop of the list.
BESIDE_THE_PANEL = (4, 4)


def shown(total: int) -> str:
    return f"{MINUS}{-total}" if total < 0 else str(total)


def answer_the_ask(person: Page, word: str) -> None:
    person.locator(ASK).get_by_role("button", name=word, exact=True).click()


def expect_the_refusal_clear_of_the_coasters(person: Page) -> None:
    line = person.locator(REFUSAL_LINE)
    expect(line).to_be_visible()
    notice = line.bounding_box()
    assert notice is not None
    for coaster in person.locator(COASTER).all():
        box = coaster.bounding_box()
        assert box is not None
        assert (
            notice["x"] + notice["width"] <= box["x"]
            or box["x"] + box["width"] <= notice["x"]
            or notice["y"] + notice["height"] <= box["y"]
            or box["y"] + box["height"] <= notice["y"]
        )


def propose_the_end(person: Page) -> None:
    """The menu's row asks a second tap, as the other armed keys do."""
    key = open_table_menu(person).locator(END_KEY)
    key.click()
    key.click()


def expect_the_sheet_inside_the_panel(person: Page) -> None:
    panel = person.locator(GAME_LIST).bounding_box()
    assert panel is not None
    for part in (".skatline .pair", ".held-row", ".trick-row"):
        for box in (each.bounding_box() for each in person.locator(f"{SHEET} {part}").all()):
            assert box is not None
            assert box["x"] >= panel["x"]
            assert box["x"] + box["width"] <= panel["x"] + panel["width"]


def expect_the_tricks_to_lay_their_cards_side_by_side_in_the_panels_one_frame(person: Page) -> None:
    panel = person.locator(GAME_LIST).bounding_box()
    sheet = person.locator(SHEET).bounding_box()
    assert panel is not None
    assert sheet is not None
    assert sheet["x"] - panel["x"] <= FRAME_PADDING
    assert panel["x"] + panel["width"] - (sheet["x"] + sheet["width"]) <= FRAME_PADDING
    for trick in person.locator(PLAYED_TRICKS).all():
        lefts = [box["x"] for box in (card.bounding_box() for card in trick.locator(".mini").all()) if box]
        assert len({round(left) for left in lefts}) == PLAYS_IN_A_TRICK, f"cards overlap at x={lefts}"


def expect_the_end_in_the_menu_and_the_bar_holding_only_weiter(person: Page) -> None:
    bar = person.locator(".actions")
    expect(open_table_menu(person).locator(END_KEY)).to_be_visible()
    close_table_menu(person)
    expect(bar.locator(END_KEY)).to_have_count(0)
    expect(bar.get_by_role("button", name=STAND_UP)).to_have_count(0)
    expect(bar.get_by_role("button", name=WEITER, exact=True)).to_be_visible()


CENTRED_WITHIN = 2
TEXT_BOX_OF = """pill => {
    const range = document.createRange();
    range.selectNodeContents(pill.querySelector(".words"));
    const text = range.getBoundingClientRect();
    const box = pill.getBoundingClientRect();
    return {
        above: text.top - box.top,
        below: box.bottom - text.bottom,
        left: text.left - box.left,
        right: box.right - text.right,
    };
}"""


def expect_the_sheet_inside_the_window(person: Page, sheet: Locator) -> None:
    """The sheet lies wholly in the window once it has settled, so its top keys stay in sight."""
    viewport = person.viewport_size
    assert viewport is not None
    sheet.evaluate("element => Promise.all(element.getAnimations().map((animation) => animation.finished))")
    box = sheet.bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= viewport["height"]


def expect_the_wait_pill_to_hold_its_text_centred(person: Page) -> None:
    """The pill is a status of the bar: its words sit wholly inside its box."""
    pill = person.locator(".actions .copy.wait")
    expect(pill).to_be_visible()
    gaps = pill.evaluate(TEXT_BOX_OF)
    assert min(gaps.values()) >= 0
    assert abs(gaps["above"] - gaps["below"]) <= CENTRED_WITHIN


def expect_the_proposal_asked(table: RamschTable) -> None:
    """The first seat proposed: the other two are asked, the proposer waits for them and the watcher only reads."""
    proposed = text(SOURCE_LANGUAGE, "table.wantsToEndSeries", name=table.names[1])
    for person in (table.pages[2], table.pages[3], table.watcher):
        expect(person.locator(ASK)).to_contain_text(proposed)
    expect(table.pages[1].locator(ASK)).to_contain_text(waiting_for([table.names[2], table.names[3]]))
    expect(table.watcher.locator(ASK).get_by_role("button")).to_have_count(0)
    for person in (table.pages[1], table.pages[2], table.pages[3]):
        expect(person.get_by_role("button", name=WEITER, exact=True)).to_have_count(0)


def expect_the_standings(person: Page, standings: list[dict[str, Any]], own_name: str | None) -> None:
    expect(person.locator(STANDING)).to_have_count(1)
    expect(person.locator(ASK)).to_have_count(0)
    expect(person.locator(COUNT)).to_have_count(0)
    expect(person.get_by_role("button", name=WEITER, exact=True)).to_have_count(0)
    rows = person.locator(f"{STANDING} .rank")
    expect(rows).to_have_count(len(standings))
    for index, standing in enumerate(standings):
        row = rows.nth(index)
        expect(row.locator(".place")).to_have_text(str(standing["place"]))
        name = YOU if standing["display_name"] == own_name else standing["display_name"]
        expect(row.locator("b")).to_have_text(name)
        expect(row.locator("small")).to_have_count(0)
        expect(row.locator(".sum")).to_have_text(shown(standing["total"]))
    expect(person.locator(f"{STANDING} .rank.win")).to_have_count(sum(standing["place"] == 1 for standing in standings))


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
    expect(first.locator(f"{GAME_LIST} .empty")).to_have_text(text(SOURCE_LANGUAGE, "table.seriesListEmpty"))
    first.keyboard.press("Escape")
    expect(first.locator(GAME_LIST)).not_to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_mark_counts_the_game_and_the_list_scrolls_inside_its_panel(
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
        expect(person.locator(ROWS)).to_have_count(2)
        newest, oldest = (row.inner_text() for row in person.locator(ROWS).all())
        assert newest.splitlines()[0] == "2"
        assert oldest.splitlines()[0] == "1"
        assert RAMSCH in newest
        # A panel taller than the room scrolls its rows, and the page stays where it is.
        person.set_viewport_size({"width": form_factor["viewport"]["width"], "height": SHORT_ROOM})
        rows = person.locator(f"{GAME_LIST} .rows")
        assert rows.evaluate("rows => rows.scrollHeight > rows.clientHeight")
        assert rows.evaluate("rows => { rows.scrollTop = rows.scrollHeight; return rows.scrollTop > 0; }")
        assert person.evaluate("window.scrollY") == 0
        person.keyboard.press("Escape")
        expect(person.locator(GAME_LIST)).not_to_be_visible()
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
    person.locator(COUNT).click()
    person.locator(ROWS).click()

    expect(person.locator(f"{SHEET} .held-row")).to_have_count(SEATS)
    expect(person.locator(PLAYED_TRICKS)).to_have_count(TRICKS_IN_A_GAME)
    # Every card of a trick names the seat that played it.
    expect(person.locator(f"{TRICKS} .by")).to_have_count(TRICKS_IN_A_GAME * PLAYS_IN_A_TRICK)
    expect_the_sheet_inside_the_panel(person)
    expect_the_tricks_to_lay_their_cards_side_by_side_in_the_panels_one_frame(person)

    # A panel shorter than its game scrolls its tricks, and neither the page nor the panel moves.
    person.set_viewport_size({"width": form_factor["viewport"]["width"], "height": SHEET_ROOM})
    tricks = person.locator(TRICKS)
    assert tricks.evaluate("tricks => tricks.scrollHeight > tricks.clientHeight")
    assert tricks.evaluate("tricks => { tricks.scrollTop = tricks.scrollHeight; return tricks.scrollTop > 0; }")
    assert person.evaluate("window.scrollY") == 0
    assert person.locator(GAME_LIST).evaluate("panel => panel.scrollTop") == 0

    person.get_by_role("button", name=SHEET_BACK).click()
    expect(person.locator(SHEET)).to_have_count(0)
    expect(person.locator(ROWS)).to_have_count(1)
    person.keyboard.press("Escape")
    expect(person.locator(GAME_LIST)).not_to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_game_with_three_putters_keeps_every_putter_and_the_skat_inside_the_panel(
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
    person.locator(COUNT).click()
    person.locator(ROWS).click()

    expect(person.locator(f"{SHEET} .skatline .pair")).to_have_count(SEATS + 1)
    lines = person.locator(f"{SHEET} .skatline .puts .pair")
    lefts = {round(box["x"]) for box in (line.bounding_box() for line in lines.all()) if box}
    assert len(lefts) == 1, f"the putters' lines start at x={lefts}"
    expect_the_sheet_inside_the_panel(person)
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
        expect(person.get_by_role("button", name=NEW_SERIES, exact=True)).to_be_visible()
        expect(person.get_by_role("button", name=WEITER, exact=True)).to_have_count(0)
    for person in table.everyone:
        expect(person.locator(STANDING)).to_have_count(1)
        expect(person.locator(COUNT)).to_have_count(0)
        expect(person.locator(f"{NEXT_LINE} .chip.official")).to_have_text(text(SOURCE_LANGUAGE, "rules.chipOfficial"))
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

    expect_the_end_in_the_menu_and_the_bar_holding_only_weiter(first)
    propose_the_end(first)
    expect_the_proposal_asked(table)

    answer_the_ask(second, YES)
    expect(second.locator(ASK)).to_contain_text(waiting_for([table.names[3]]))
    answer_the_ask(third, YES)

    # The last tap returns before the stream brings the end, so the view is read once every page shows the standings.
    for person in table.everyone:
        expect(person.locator(STANDING)).to_have_count(1)
    series = table.view(1)["series"]
    assert series["over"] is True
    for seat, person in table.pages.items():
        expect_the_standings(person, series["standings"], table.names[seat])
    expect_the_standings(table.watcher, series["standings"], None)
    watching = text(SOURCE_LANGUAGE, "table.watchingOnly")
    expect(table.watcher.get_by_text(watching)).to_be_visible()
    expect(table.watcher.get_by_role("button", name=NEW_SERIES, exact=True)).to_have_count(0)

    first.get_by_role("button", name=NEW_SERIES, exact=True).click()
    second.get_by_role("button", name=NEW_SERIES, exact=True).click()
    for person in table.everyone:
        expect(person.locator(".chair[data-seat='1'] .mark.ready")).to_have_count(1)
        expect(person.locator(".chair[data-seat='2'] .mark.ready")).to_have_count(1)
        expect(person.locator(STANDING)).to_have_count(1)
    expect(first.locator(".copy.wait")).to_contain_text(waiting_for([table.names[3]]))
    expect_the_wait_pill_to_hold_its_text_centred(first)

    third.get_by_role("button", name=NEW_SERIES, exact=True).click()
    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(game_count(1))
        expect(person.locator(STANDING)).to_have_count(0)
        expect(person.locator(".chair .coaster")).to_have_text(["0", "0", "0"])
    assert page_errors == []


def expect_the_minute_below_the_card(person: Page) -> None:
    """The running minute is a pill of its own below the standings card, never a line inside it."""
    card = person.locator(".result.standing").bounding_box()
    minute = person.locator(ANSWER_CLOCK).bounding_box()
    assert card is not None
    assert minute is not None
    assert minute["y"] >= card["y"] + card["height"]


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
        expect(person.locator(STANDING)).to_have_count(1)
        expect(person.locator(NEXT_LINE)).to_have_count(1)
        expect(person.locator(ANSWER_CLOCK)).to_have_count(0)
    for person in table.pages.values():
        expect(person.locator(".actions button")).to_have_text([NEW_SERIES, STOP_PLAYING])
    expect(table.watcher.locator(".actions button")).to_have_count(0)

    first.get_by_role("button", name=NEW_SERIES, exact=True).click()
    for person in table.everyone:
        expect(person.locator(ANSWER_CLOCK)).to_have_count(1)
        expect(person.locator(".chair[data-seat='1'] .mark.ready")).to_have_count(1)
        expect_the_minute_below_the_card(person)

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
    first.get_by_role("button", name=NEW_SERIES, exact=True).click()
    for person in table.everyone:
        expect(person.locator(ANSWER_CLOCK)).to_have_count(1)

    second.get_by_role("button", name=CHANGE, exact=True).click()
    sheet = second.locator(NEXT_SHEET)
    expect(sheet).to_be_visible()
    expect_the_sheet_inside_the_window(second, sheet)
    expect(sheet.get_by_role("spinbutton")).to_have_attribute("aria-valuenow", str(SERIES_LENGTH))
    expect(sheet.locator(".takeback")).to_be_visible()
    expect(sheet.locator(".clockline")).to_be_visible()
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
        expect(person.locator(f"{NEXT_LINE} .chip.len")).to_have_text(longer)
        expect(person.locator(".chair .mark.ready")).to_have_count(0)
        expect(person.locator(ANSWER_CLOCK)).to_have_count(0)
    expect(second.locator(NEXT_SHEET)).to_have_count(0)

    for person in table.pages.values():
        person.get_by_role("button", name=NEW_SERIES, exact=True).click()
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
        expect(person.locator(ASK)).to_have_count(0)
        expect(person.locator(".chair[data-seat='2'] .mark.declined")).to_have_count(1)
        expect_the_refusal_clear_of_the_coasters(person)
    expect(first.get_by_role("button", name=WEITER, exact=True)).to_be_visible()
    expect(open_table_menu(first).locator(END_KEY)).to_have_count(0)
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

    expect(first.locator(f"{GAME_LIST} [role=alert]")).to_have_text(text(SOURCE_LANGUAGE, "table.seriesListFailed"))
    first.mouse.click(*BESIDE_THE_PANEL)
    expect(first.locator(GAME_LIST)).not_to_be_visible()
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

    expect(first.locator(".note")).to_have_text(COMMAND_FAILED)
    expect(first.locator(END_KEY)).to_be_enabled()
    for person in (table.pages[2], table.pages[3]):
        expect(person.locator(ASK)).to_have_count(0)
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
        expect(person.locator(STANDING)).to_have_count(1)

    menu_button(table.pages[3], STAND_UP).click()

    for person in table.everyone:
        leaver = person.locator(f"{STANDING} .rank b", has_text=table.names[3])
        expect(leaver.locator("em")).to_have_text(GONE)
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
        person.get_by_role("button", name=NEW_SERIES, exact=True).click()
    expect(first.locator(ANSWER_CLOCK)).to_have_count(1)

    menu_button(third, STAND_UP).click()

    for person in (first, second):
        expect(person.locator(ANSWER_CLOCK)).to_have_count(0)
        expect(person.locator(".copy.wait")).to_have_text(text(SOURCE_LANGUAGE, "table.waitingForPlayers"))
        expect(person.get_by_role("button", name=NEW_SERIES, exact=True)).to_have_count(0)
    for seat in (1, 2):
        expect(first.locator(f".chair[data-seat='{seat}'] .mark.ready")).to_have_count(1)
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

    expect(proposer.locator(ASK)).to_contain_text(text(SOURCE_LANGUAGE, "table.waitingForPlayers"))
    expect(proposer.locator(ASK).locator(".face")).to_have_count(0)
    assert page_errors == []
