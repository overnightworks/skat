from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.ramsch import RamschTable
from tests.e2e.support.result_card import MINUS, waiting_for

if TYPE_CHECKING:
    from collections.abc import Callable

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
NEW_SERIES = text(SOURCE_LANGUAGE, "table.newSeries")
RAMSCH = text(SOURCE_LANGUAGE, "game.ramsch")
YES = text(SOURCE_LANGUAGE, "table.yes")
NO = text(SOURCE_LANGUAGE, "table.no")


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

    propose_the_end(first)
    for person in (second, third):
        expect(person.locator(ASK)).to_contain_text(
            text(SOURCE_LANGUAGE, "table.wantsToEndSeries", name=table.names[1])
        )
    expect(first.locator(ASK)).to_contain_text(waiting_for([table.names[2], table.names[3]]))
    expect(table.watcher.locator(ASK)).to_contain_text(
        text(SOURCE_LANGUAGE, "table.wantsToEndSeries", name=table.names[1])
    )
    expect(table.watcher.locator(ASK).get_by_role("button")).to_have_count(0)

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

    third.get_by_role("button", name=NEW_SERIES, exact=True).click()
    for person in table.everyone:
        expect(person.locator(COUNT)).to_have_text(game_count(1))
        expect(person.locator(STANDING)).to_have_count(0)
        expect(person.locator(".chair .coaster")).to_have_text(["0", "0", "0"])
    assert page_errors == []
