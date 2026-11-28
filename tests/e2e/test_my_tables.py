import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.table.records import SERIES_LENGTH_DEFAULT, OccupantKind
from skat.web.lobby import LOBBY_EVENTS_PATH, LobbyChairAnswer, LobbyTableAnswer, MineAnswer
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.table_menu import menu_button
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

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

MY_TABLES = text(SOURCE_LANGUAGE, "lobby.myTables")
YOU = text(SOURCE_LANGUAGE, "lobby.sideYou")
SEAT_FREE = text(SOURCE_LANGUAGE, "lobby.seatFree")
SEAT_AWAY = text(SOURCE_LANGUAGE, "lobby.seatAway")
YOUR_TURN = text(SOURCE_LANGUAGE, "lobby.chipYourTurn")
RECONNECTING = text(SOURCE_LANGUAGE, "app.reconnecting")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
LENGTH = text(SOURCE_LANGUAGE, "lobby.length", count=SERIES_LENGTH_DEFAULT)
RESULT_WAITS = text(SOURCE_LANGUAGE, "lobby.chipResultWaits")
SERIES_OVER = text(SOURCE_LANGUAGE, "lobby.chipSeriesOver")
ENDS_IN_DAYS = re.compile(r"endet in \d+ Tagen")
EVENT_STREAM = "text/event-stream"
SEAT_COUNT = 3


def title_of(opener: str) -> str:
    return text(SOURCE_LANGUAGE, "lobby.title", name=opener)


def card_of(person: Page, opener: str) -> Locator:
    """The card that opens the table `opener` opened.

    An account keeps the tables of every test that signed in as it, so each test's opener has a name no other uses.
    """
    return person.get_by_role("link", name=text(SOURCE_LANGUAGE, "lobby.openTable", title=title_of(opener)))


def free_chairs_of(card: Locator) -> Locator:
    return card.get_by_text(SEAT_FREE, exact=True)


@pytest.fixture
def deal_a_table_of_its_own(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., DeclaringTable]:
    """A dealt table whose three people sit at no other table, so each one's list holds the one card of its opener."""

    def deal(form_factor: dict[str, Any], opener: str) -> DeclaringTable:
        return DeclaringTable(
            open_person,
            e2e_server,
            member_of,
            page_errors,
            form_factor,
            opener_name=opener,
            joiners=(f"{opener}-zwei", f"{opener}-drei"),
        )

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_sees_the_table_he_sits_at_and_one_tap_opens_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    name = f"Bert{form_factor['viewport']['width']}"
    person = record_page_errors(open_person(username=name, **form_factor), page_errors)
    path = open_new_table(person, e2e_server)

    open_start_page(person, e2e_server)

    expect(person.get_by_role("heading", name=MY_TABLES)).to_be_visible()
    card = card_of(person, name)
    expect(card).to_contain_text(LENGTH)
    expect(card.get_by_text(YOU, exact=True)).to_be_visible()
    expect(free_chairs_of(card)).to_have_count(2)

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
    card = card_of(host, "Hanna")
    expect(free_chairs_of(card)).to_have_count(2)

    sit_in(guest, 2)

    expect(card.get_by_text("Gero", exact=True)).to_be_visible()
    expect(free_chairs_of(card)).to_have_count(1)
    menu_button(guest, STAND_UP).click()
    expect(card.get_by_text("Gero", exact=True)).to_have_count(0)
    expect(free_chairs_of(card)).to_have_count(2)
    assert_never_reloaded(host)


def test_a_member_who_sits_at_no_table_has_no_meine_tische_and_another_members_table_is_no_link_of_his(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    other = record_page_errors(open_person(username="Olga", **DESKTOP), page_errors)
    open_new_table(other, e2e_server)
    lonely = record_page_errors(open_person(username="Lukas", **DESKTOP), page_errors)

    open_start_page(lonely, e2e_server)

    expect(lonely.get_by_role("heading", name=MY_TABLES)).to_have_count(0)
    expect(lonely.get_by_role("heading", name=title_of("Olga"))).to_be_visible()
    expect(card_of(lonely, "Olga")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_chip_and_the_ring_follow_whose_turn_it_is(
    deal_a_table_of_its_own: Callable[..., DeclaringTable],
    e2e_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    opener = f"Selma{form_factor['viewport']['width']}"
    table = deal_a_table_of_its_own(form_factor, opener)
    declarer_name = table.name_of_the_declarer()
    waiting = table.others[0]

    open_start_page(table.declarer, e2e_server)
    open_start_page(waiting, e2e_server)

    own_card = card_of(table.declarer, opener)
    expect(own_card.get_by_text(YOUR_TURN, exact=True)).to_be_visible()
    expect(own_card.locator(".lobby-seat.turn")).to_have_count(1)
    other_card = card_of(waiting, opener)
    expect(other_card.get_by_text(YOUR_TURN, exact=True)).to_have_count(0)
    expect(other_card.locator(".lobby-seat.turn .lobby-plate b")).to_have_text(declarer_name)


def test_a_dealt_table_everybody_left_shows_the_away_marks_and_its_end(
    deal_a_table_of_its_own: Callable[..., DeclaringTable], e2e_server: RunningServer
) -> None:
    table = deal_a_table_of_its_own(DESKTOP, "Thekla")
    for person in (table.declarer, *table.others, table.watcher):
        open_start_page(person, e2e_server)

    card = card_of(table.declarer, "Thekla")

    expect(card.get_by_title(SEAT_AWAY, exact=True)).to_have_count(SEAT_COUNT)
    expect(card.get_by_text(ENDS_IN_DAYS)).to_have_count(1)


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


def test_every_away_chair_of_an_undealt_table_says_its_minutes_and_a_lost_line_keeps_the_list_until_it_is_back(
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

    card = card_of(person, "Mara")
    expect(card.get_by_title(SEAT_AWAY, exact=True)).to_have_count(2)
    expect(
        card.get_by_title(text(SOURCE_LANGUAGE, "lobby.otherSeatFreeIn", count=5, minutes="5", name="Mara"), exact=True)
    ).to_have_text(text(SOURCE_LANGUAGE, "lobby.minutesLeft", count=5, minutes="5"))
    expect(
        card.get_by_title(text(SOURCE_LANGUAGE, "lobby.ownSeatFreeIn", count=4, minutes="4"), exact=True)
    ).to_have_text(text(SOURCE_LANGUAGE, "lobby.minutesLeft", count=4, minutes="4"))
    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    expect(card).to_be_visible()
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_enabled()

    line["state"] = "back"

    expect(person.get_by_role("status").filter(has_text=RECONNECTING)).to_have_count(0)


@pytest.mark.parametrize(
    ("series_over", "chip_text", "other_chip_text"),
    [(False, RESULT_WAITS, SERIES_OVER), (True, SERIES_OVER, RESULT_WAITS)],
    ids=["result", "series-over"],
)
def test_a_stood_result_and_a_finished_series_each_show_their_own_chip(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    series_over: bool,
    chip_text: str,
    other_chip_text: str,
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

    card = card_of(person, "Mara")
    expect(card.get_by_text(chip_text, exact=True)).to_be_visible()
    expect(card.get_by_text(other_chip_text, exact=True)).to_have_count(0)


def test_going_back_from_a_table_returns_to_a_current_list(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="Rita", **DESKTOP), page_errors)
    path = open_new_table(person, e2e_server)
    open_start_page(person, e2e_server)

    card_of(person, "Rita").click()
    expect(person).to_have_url(f"{e2e_server.base_url}{path}")
    person.go_back()

    expect(card_of(person, "Rita")).to_be_visible()
