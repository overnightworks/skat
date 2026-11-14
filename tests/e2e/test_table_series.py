from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import Page, expect

from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RamschTable
from tests.e2e.support.result_card import MINUS, waiting_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Route

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SERIES_LENGTH = 3
# A room this short cannot show two rows of the list beside its heading.
SHORT_ROOM = 160
COUNT = ".series-count"
GAME_LIST = ".game-list"
ROWS = f"{GAME_LIST} .grow"
STANDING = ".result.standing"
ASK = ".plaque.ask"
END_KEY = ".actions .end-series"
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
PHONE_BREAKPOINT = 900
NEW_SERIES = text(SOURCE_LANGUAGE, "table.newSeries")
RAMSCH = text(SOURCE_LANGUAGE, "game.ramsch")
YES = text(SOURCE_LANGUAGE, "table.yes")
NO = text(SOURCE_LANGUAGE, "table.no")
GONE = text(SOURCE_LANGUAGE, "table.seriesGone")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
REFUSED = 409
# A point of the room outside the centred panel, where a tap lands on the backdrop of the list.
BESIDE_THE_PANEL = (4, 4)


def refuse(route: Route) -> None:
    route.fulfill(status=REFUSED, content_type="application/json", body="{}")


def game_count(game: int) -> str:
    return text(SOURCE_LANGUAGE, "table.seriesCount", game=str(game), count=SERIES_LENGTH)


def shown(total: int) -> str:
    return f"{MINUS}{-total}" if total < 0 else str(total)


class PassedInTable(RamschTable):
    """The same three people at a table without Ramsch, so a hand all pass is passed in and leaves no entry."""

    options: ClassVar[dict[str, Any]] = {}


def answer_the_ask(person: Page, word: str) -> None:
    person.locator(ASK).get_by_role("button", name=word, exact=True).click()


def propose_the_end(person: Page) -> None:
    """The key asks a second tap, as the other armed keys do."""
    key = person.locator(END_KEY)
    key.click()
    key.click()


def expect_the_keys_in_one_row(person: Page) -> None:
    bar = person.locator(".actions")
    keys = (
        bar.locator(".end-series"),
        bar.get_by_role("button", name=WEITER, exact=True),
        bar.get_by_role("button", name=STAND_UP),
    )
    boxes = [key.bounding_box() for key in keys]
    tops = [box["y"] for box in boxes if box is not None]
    assert len(tops) == len(keys)
    assert max(tops) - min(tops) <= 1


TABLE_SCENES = Path(__file__).parents[2] / "docs" / "mockups" / "table.html"
FONT_SIZE_OF = "element => getComputedStyle(element).fontSize"
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


def the_scene_draws_the_wait_pill_in(person: Page) -> str:
    """The type size of the pill in the frozen scene series-next at the person's width, read from the scene itself."""
    viewport = person.viewport_size
    assert viewport is not None
    frame = "series-next-1280" if viewport["width"] >= PHONE_BREAKPOINT else "series-next-390"
    scene = person.context.new_page()
    try:
        scene.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        return scene.locator(f"[id='{frame}'] .cb.wide.glass", has_text=waiting_for(["Ben"])).evaluate(FONT_SIZE_OF)
    finally:
        scene.close()


def expect_the_wait_pill_to_hold_its_text_centred(person: Page) -> None:
    """The pill is a status of the bar: its words sit wholly inside its box, as the frozen scene draws them."""
    pill = person.locator(".actions .copy.wait")
    expect(pill).to_be_visible()
    gaps = pill.evaluate(TEXT_BOX_OF)
    assert min(gaps.values()) >= 0
    assert abs(gaps["above"] - gaps["below"]) <= CENTRED_WITHIN
    assert pill.evaluate(FONT_SIZE_OF) == the_scene_draws_the_wait_pill_in(person)


def expect_the_proposal_asked(table: RamschTable) -> None:
    """The first seat proposed: the other two are asked, the proposer waits for them and the watcher only reads."""
    proposed = text(SOURCE_LANGUAGE, "table.wantsToEndSeries", name=table.names[1])
    for person in (table.pages[2], table.pages[3], table.watcher):
        expect(person.locator(ASK)).to_contain_text(proposed)
    expect(table.pages[1].locator(ASK)).to_contain_text(waiting_for([table.names[2], table.names[3]]))
    expect(table.watcher.locator(ASK).get_by_role("button")).to_have_count(0)


def expect_the_standings(person: Page, standings: list[dict[str, Any]]) -> None:
    expect(person.locator(STANDING)).to_have_count(1)
    expect(person.locator(ASK)).to_have_count(0)
    expect(person.locator(COUNT)).to_have_count(0)
    expect(person.get_by_role("button", name=WEITER, exact=True)).to_have_count(0)
    rows = person.locator(f"{STANDING} .rank")
    expect(rows).to_have_count(len(standings))
    for index, standing in enumerate(standings):
        row = rows.nth(index)
        expect(row.locator(".place")).to_have_text(str(standing["place"]))
        expect(row.locator("b")).to_contain_text(standing["display_name"])
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

    expect(first.locator(END_KEY)).to_be_visible()
    if form_factor["viewport"]["width"] < PHONE_BREAKPOINT:
        expect_the_keys_in_one_row(first)
    propose_the_end(first)
    expect_the_proposal_asked(table)

    answer_the_ask(second, NO)
    for person in table.everyone:
        expect(person.locator(ASK)).to_have_count(0)

    propose_the_end(first)
    answer_the_ask(second, YES)
    expect(second.locator(ASK)).to_contain_text(waiting_for([table.names[3]]))
    answer_the_ask(third, YES)

    # The last tap returns before the stream brings the end, so the view is read once every page shows the standings.
    for person in table.everyone:
        expect(person.locator(STANDING)).to_have_count(1)
    series = table.view(1)["series"]
    assert series["over"] is True
    for person in table.everyone:
        expect_the_standings(person, series["standings"])
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

    table.pages[3].get_by_role("button", name=STAND_UP, exact=True).click()

    for person in table.everyone:
        leaver = person.locator(f"{STANDING} .rank b", has_text=table.names[3])
        expect(leaver.locator("em")).to_have_text(GONE)
    assert page_errors == []
