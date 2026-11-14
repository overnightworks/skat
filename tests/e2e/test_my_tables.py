import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.table.records import SERIES_LENGTH_DEFAULT, OccupantKind
from skat.web.lobby import LOBBY_EVENTS_PATH, LobbyChairAnswer, LobbyTableAnswer, MineAnswer
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.tables import (
    TABLE_URL,
    assert_never_reloaded,
    mark_page,
    open_new_table,
    open_start_page,
    sit_in,
    watch,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.declaring import DeclaringTable
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

MY_TABLES = text(SOURCE_LANGUAGE, "lobby.myTables")
YOU = text(SOURCE_LANGUAGE, "lobby.sideYou")
SEAT_FREE = text(SOURCE_LANGUAGE, "lobby.seatFree")
YOUR_TURN = text(SOURCE_LANGUAGE, "lobby.chipYourTurn")
RECONNECTING = text(SOURCE_LANGUAGE, "app.reconnecting")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
LENGTH = text(SOURCE_LANGUAGE, "lobby.length", count=SERIES_LENGTH_DEFAULT)
RESULT_WAITS = text(SOURCE_LANGUAGE, "lobby.chipResultWaits")
SERIES_OVER = text(SOURCE_LANGUAGE, "lobby.chipSeriesOver")
ENDS_IN_DAYS = re.compile(r"endet in \d+ Tagen")
# A tap target is at least this many CSS pixels on each side.
TAP_TARGET_PIXELS = 44
EVENT_STREAM = "text/event-stream"
SEAT_COUNT = 3


def card_of(person: Page, path: str):
    """The card that opens the table at `path`: an account keeps the tables of every test that signed in as it."""
    return person.locator(f"a.lobby-card[href='{path}']")


def card_named(person: Page, owner: str):
    return person.get_by_role("link", name=text(SOURCE_LANGUAGE, "lobby.openTable", title=owner))


def plates_of(card) -> Any:
    return card.locator(".lobby-plate b")


def chip_texts_of(card) -> Any:
    return card.locator(".lobby-chips .chip")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_sees_the_table_he_sits_at_and_one_tap_opens_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="Bert", **form_factor), page_errors)
    path = open_new_table(person, e2e_server)

    open_start_page(person, e2e_server)

    expect(person.get_by_role("heading", name=MY_TABLES)).to_be_visible()
    card = card_of(person, path)
    expect(card).to_have_count(1)
    expect(card).to_have_attribute("aria-label", text(SOURCE_LANGUAGE, "lobby.openTable", title="Berts Tisch"))
    expect(card).to_contain_text(LENGTH)
    expect(plates_of(card)).to_have_text([YOU, SEAT_FREE, SEAT_FREE])
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    for box in (card.bounding_box(), person.get_by_role("button", name=NEW_TABLE_BUTTON).bounding_box()):
        assert box is not None
        assert box["height"] >= TAP_TARGET_PIXELS
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= form_factor["viewport"]["width"]

    card.click()

    expect(person).to_have_url(TABLE_URL)
    assert person.url.endswith(path)


def test_the_list_follows_another_person_sitting_down_and_standing_up_without_a_reload(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    host = record_page_errors(open_person(username="Hanna", **DESKTOP), page_errors)
    path = open_new_table(host, e2e_server)
    guest = record_page_errors(open_person(username="Gero", **DESKTOP), page_errors)
    watch(guest, e2e_server, path)
    open_start_page(host, e2e_server)
    mark_page(host)
    card = card_of(host, path)
    expect(plates_of(card)).to_have_text([YOU, SEAT_FREE, SEAT_FREE])

    sit_in(guest, 2)

    expect(plates_of(card)).to_have_text([YOU, "Gero", SEAT_FREE])
    guest.get_by_role("button", name=STAND_UP).click()
    expect(plates_of(card)).to_have_text([YOU, SEAT_FREE, SEAT_FREE])
    assert_never_reloaded(host)


def test_a_member_who_sits_at_no_table_has_no_meine_tische_and_another_members_table_is_no_link_of_his(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    other = record_page_errors(open_person(username="Olga", **DESKTOP), page_errors)
    open_new_table(other, e2e_server)
    lonely = record_page_errors(open_person(username="Lukas", **DESKTOP), page_errors)

    open_start_page(lonely, e2e_server)

    expect(lonely.get_by_role("heading", name=MY_TABLES)).to_have_count(0)
    expect(lonely.locator("a.lobby-card")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_chip_and_the_ring_follow_whose_turn_it_is(
    deal_a_declaring_table: Callable[..., DeclaringTable],
    e2e_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer_name = table.name_of_the_declarer()
    table_path = f"{TABLE_PAGE_PREFIX}{table.table_id}"
    waiting = table.others[0]

    open_start_page(table.declarer, e2e_server)
    open_start_page(waiting, e2e_server)

    own_card = card_of(table.declarer, table_path)
    expect(chip_texts_of(own_card)).to_have_text([YOUR_TURN])
    expect(chip_texts_of(own_card).first).to_have_class(re.compile(r"\bnow\b"))
    expect(own_card.locator(".lobby-seat.turn")).to_have_count(1)
    other_card = card_of(waiting, table_path)
    expect(chip_texts_of(other_card)).to_have_count(0)
    expect(other_card.locator(".lobby-seat.turn .lobby-plate b")).to_have_text(declarer_name)


def test_a_dealt_table_everybody_left_shows_the_away_marks_and_its_end(
    deal_a_declaring_table: Callable[..., DeclaringTable], e2e_server: RunningServer
) -> None:
    table = deal_a_declaring_table(DESKTOP)
    for person in (table.declarer, *table.others, table.watcher):
        open_start_page(person, e2e_server)

    card = card_of(table.declarer, f"{TABLE_PAGE_PREFIX}{table.table_id}")

    expect(card.locator(".lobby-seat.away")).to_have_count(SEAT_COUNT)
    expect(card.locator(".lobby-chips .chip", has_text=ENDS_IN_DAYS)).to_have_count(1)


def mine_event(table: LobbyTableAnswer) -> str:
    """The stream's `mine` event carrying the one table."""
    return f"event: mine\ndata: {MineAnswer(tables=[table]).model_dump_json()}\n\n"


def waiting_table(opener: str, hold_seconds_left: dict[int, int] | None = None) -> LobbyTableAnswer:
    """A table where no hand was dealt, the own chair and the opener's away, the third chair free.

    The chairs named by seat in `hold_seconds_left` hold their place for that many seconds.
    """
    holds = hold_seconds_left or {}

    def chair(seat: int, name: str | None, *, mine: bool) -> LobbyChairAnswer:
        return LobbyChairAnswer(
            seat=seat,
            occupant_name=name,
            occupant_kind=None if name is None else OccupantKind.PERSON,
            is_mine=mine,
            ready=False,
            total=None,
            is_away=name is not None and not mine,
            is_turn=False,
            hold_seconds_left=holds.get(seat),
        )

    return LobbyTableAnswer(
        id="c" * 32,
        private=False,
        title_name=opener,
        game_number=0,
        game_count=SERIES_LENGTH_DEFAULT,
        dealt=False,
        awaits_you=False,
        waits_on=None,
        result_waits=False,
        series_over=False,
        ends_at=None,
        chairs=[chair(0, opener, mine=False), chair(1, "Dina", mine=True), chair(2, None, mine=False)],
    )


def test_every_away_chair_of_an_undealt_table_says_its_minutes_and_a_lost_line_dims_the_list_until_it_is_back(
    open_person: Callable[..., Page], e2e_server: RunningServer, expected_request_failures: list[str]
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(username="Dina", **DESKTOP)
    line = {"state": "first"}

    def answer(route: Route) -> None:
        if line["state"] == "back":
            route.continue_()
            return
        if line["state"] == "lost":
            route.abort()
            return
        route.fulfill(
            status=200,
            headers={"content-type": EVENT_STREAM},
            body=mine_event(waiting_table("Mara", {0: 300, 1: 240})),
        )
        # The stream ends with its first list, so the line stays lost until the test brings it back.
        line["state"] = "lost"

    person.route(f"**{LOBBY_EVENTS_PATH}", answer)

    person.goto(f"{e2e_server.base_url}/")

    card = card_named(person, "Maras Tisch")
    expect(card.locator(".lobby-seat.away")).to_have_count(2)
    expect(card.locator(".lobby-plate small")).to_have_text(
        [
            text(SOURCE_LANGUAGE, "lobby.minutesLeft", count=5, minutes="5"),
            text(SOURCE_LANGUAGE, "lobby.minutesLeft", count=4, minutes="4"),
        ]
    )
    expect(card.locator(".lobby-plate small").nth(1)).to_have_attribute(
        "title", text(SOURCE_LANGUAGE, "lobby.ownSeatFreeIn", count=4, minutes="4")
    )
    expect(card.locator(".lobby-plate small").first).to_have_attribute(
        "title", text(SOURCE_LANGUAGE, "lobby.otherSeatFreeIn", count=5, minutes="5", name="Mara")
    )
    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    expect(person.locator(".lobby-lists")).to_have_class(re.compile(r"\bstale\b"))
    expect(card).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_enabled()

    line["state"] = "back"

    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_have_count(0)
    expect(person.locator(".lobby-lists.stale")).to_have_count(0)


@pytest.mark.parametrize(
    ("series_over", "chip_text"), [(False, RESULT_WAITS), (True, SERIES_OVER)], ids=["result", "series-over"]
)
def test_a_stood_result_and_a_finished_series_each_draw_their_chip_with_the_trophy(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    series_over: bool,
    chip_text: str,
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(username="Dina", **DESKTOP)
    table = waiting_table("Mara").model_copy(update={"result_waits": True, "series_over": series_over})
    fulfilled = {"once": False}

    def answer(route: Route) -> None:
        if fulfilled["once"]:
            route.abort()
            return
        fulfilled["once"] = True
        route.fulfill(status=200, headers={"content-type": EVENT_STREAM}, body=mine_event(table))

    person.route(f"**{LOBBY_EVENTS_PATH}", answer)

    person.goto(f"{e2e_server.base_url}/")

    chip = chip_texts_of(card_named(person, "Maras Tisch"))
    expect(chip).to_have_text([chip_text])
    expect(chip.locator("svg")).to_have_count(1)


def test_going_back_from_a_table_returns_to_a_current_list(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="Rita", **DESKTOP), page_errors)
    path = open_new_table(person, e2e_server)
    open_start_page(person, e2e_server)

    card_of(person, path).click()
    expect(person).to_have_url(f"{e2e_server.base_url}{path}")
    person.go_back()

    expect(card_of(person, path)).to_be_visible()
