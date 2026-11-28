"""A look that draws the whole table tells each chair by role and name, and says a seat sentence once."""

from functools import partial
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.mcp import SIT_DOWN_TOOL
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.conftest import Look
from tests.e2e.support.bidding import answer_of, dealt_table
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import DESKTOP, McpAgent
from tests.e2e.support.tables import open_new_table, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

TABLE = text(SOURCE_LANGUAGE, "table.landmark")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
FREE_CHAIR = text(SOURCE_LANGUAGE, "table.chairFree")
AGENT = text(SOURCE_LANGUAGE, "table.chairAgent")
AWAY = text(SOURCE_LANGUAGE, "table.seatAway")
DEALER = text(SOURCE_LANGUAGE, "table.dealer")
ON_TURN = text(SOURCE_LANGUAGE, "table.chairOnTurn")
FOREHAND = text(SOURCE_LANGUAGE, "game.forehand")
MIDDLEHAND = text(SOURCE_LANGUAGE, "game.middlehand")
REARHAND = text(SOURCE_LANGUAGE, "game.rearhand")
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
SIT_QUESTION = text(SOURCE_LANGUAGE, "table.sitQuestion")
AGENT_SEAT = 3


def cards(count: int) -> str:
    return text(SOURCE_LANGUAGE, "table.chairCards", count=count)


def chair(person: Page, *facts: str) -> Locator:
    """The chair whose whole name is these facts in their order."""
    return person.get_by_role("main", name=TABLE).get_by_role("group", name=", ".join(facts), exact=True)


def open_at(open_person: Callable[..., Page], page_errors: list[str], address: str, username: str) -> Page:
    """A page of this person at the table's address, on the look the test runs on."""
    person = record_page_errors(open_person(username=username, **DESKTOP), page_errors)
    person.goto(address)
    expect(person.get_by_role("main", name=TABLE).get_by_role("group")).to_have_count(3)
    return person


def test_each_chair_tells_whether_the_viewer_a_person_an_agent_or_nobody_sits_there_and_who_is_away(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    anna = record_page_errors(open_person(username="anna", look=Look.TODAY, **DESKTOP), page_errors)
    path = open_new_table(anna, e2e_server)
    agent = McpAgent(e2e_server, "agent-subject-mozart-on-a-chair")
    agent.request("tools/list")
    sat_failed, _ = agent.call(SIT_DOWN_TOOL, table_id=table_id_of(path), seat=AGENT_SEAT, command_id="chairs-sit-0001")
    assert not sat_failed
    chairs = anna.request.get(f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(path)}").json()["chairs"]
    agent_name = chairs[AGENT_SEAT - 1]["occupant_name"]

    watcher = open_at(open_person, page_errors, anna.url, "dora")

    expect(chair(watcher, "anna")).to_be_visible()
    expect(chair(watcher, FREE_CHAIR)).to_be_visible()
    expect(chair(watcher, agent_name, AGENT)).to_be_visible()

    own = open_at(open_person, page_errors, anna.url, "anna")

    expect(chair(own, YOU)).to_be_visible()
    expect(chair(own, "anna")).to_have_count(0)

    own.close()
    anna.close()

    expect(chair(watcher, "anna", AWAY)).to_be_visible()
    expect(chair(watcher, "anna")).to_have_count(0)


def test_in_the_auction_each_chair_tells_its_position_the_dealer_the_cards_left_and_whose_turn_it_is(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    table = dealt_table(partial(open_person, look=Look.TODAY), e2e_server, page_errors, DESKTOP)
    names = {
        seated["hand"]["position"]: seated["occupant_name"] for seated in answer_of(table.watcher, table)["chairs"]
    }

    viewer = open_at(open_person, page_errors, table.watcher.url, "erik")

    expect(chair(viewer, names["forehand"], FOREHAND, cards(10))).to_be_visible()
    expect(chair(viewer, names["middlehand"], MIDDLEHAND, cards(10), ON_TURN)).to_be_visible()
    expect(chair(viewer, names["rearhand"], REARHAND, DEALER, cards(10))).to_be_visible()


def test_in_the_play_the_turn_and_the_cards_left_follow_each_card(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal_playing_table(partial(open_person, look=Look.TODAY), e2e_server, member_of, page_errors, DESKTOP)
    forehand, middlehand = (table.names[table.seat_at[position]] for position in ("forehand", "middlehand"))
    viewer = open_at(open_person, page_errors, table.watcher.url, "erik")

    expect(chair(viewer, forehand, FOREHAND, cards(10), ON_TURN)).to_be_visible()
    expect(chair(viewer, middlehand, MIDDLEHAND, cards(10))).to_be_visible()

    table.play_out(1)

    expect(chair(viewer, forehand, FOREHAND, cards(9))).to_be_visible()
    expect(chair(viewer, middlehand, MIDDLEHAND, cards(10), ON_TURN)).to_be_visible()


def test_the_page_says_once_who_left_a_chair_and_who_plays_on(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal_playing_table(partial(open_person, look=Look.TODAY), e2e_server, member_of, page_errors, DESKTOP)
    leaver_seat = table.seat_at["rearhand"]
    viewer = open_at(open_person, page_errors, table.watcher.url, "erik")
    said = viewer.get_by_role("status")
    expect(said).to_have_count(1)
    expect(said).to_be_empty()

    table.stand_up_through_the_api(leaver_seat)

    expect(said).to_have_text(text(SOURCE_LANGUAGE, "table.standUpNotice", name=table.names[leaver_seat]))
    expect(said).to_have_count(1)
    expect(chair(viewer, FREE_CHAIR)).to_be_visible()

    free_chair = table.watcher.locator(f".chair[data-seat='{leaver_seat}']")
    free_chair.get_by_role("button", name=SIT_DOWN).click()
    table.watcher.get_by_role("dialog", name=SIT_QUESTION).get_by_role("button", name=SIT_DOWN).click()

    expect(chair(viewer, FREE_CHAIR)).to_have_count(0)
    sitter = table.view(table.seat_at["forehand"])["chairs"][leaver_seat - 1]["occupant_name"]
    expect(said).to_have_text(text(SOURCE_LANGUAGE, "table.playsOn", name=sitter))
    expect(said).to_have_count(1)
