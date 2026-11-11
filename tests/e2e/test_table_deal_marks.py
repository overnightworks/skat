import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect
from sqlalchemy import delete, update

from skat.store.schema import hand_cards, tables
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.tables import open_new_table, table_id_of
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Locator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
SIT_DOWN = catalog_text("sitDown")
STAND_UP = catalog_text("standUp")
COMMAND_FAILED = catalog_text("commandFailed")
SEAT_AWAY = catalog_text("seatAway")
DEALER = catalog_text("dealer")
USUAL_TIMEOUT_SECONDS = 5
POLL_MILLISECONDS = 100
SKAT_CARD = ".skat-card"
MAIN_STEP = ".bid-buttons .button-stage"
# The page's chairs reduced to what a hand draws on them; the keys are this test's own, compared with the answer's.
DRAWN_TABLE = """() => ({
    skat: document.querySelectorAll('.skat-card').length,
    chairs: [...document.querySelectorAll('.chair')].map((chair) => ({
        seat: Number(chair.dataset.seat),
        backs: chair.querySelectorAll('.fan .card-back').length,
        count: chair.querySelector('.count-tag')?.textContent.trim() ?? null,
        position: chair.querySelector('.mark.pos')?.textContent.trim() ?? null,
        dealer: chair.querySelector('.mark.dealer')?.textContent.trim() ?? null,
        away: chair.querySelector('.mark.away') !== null,
    })).sort((one, other) => one.seat - other.seat),
})"""
EMPTY_CHAIRS = """() => document.querySelectorAll(
    '.fan, .skat-card, .count-tag, .mark.pos, .mark.dealer'
).length"""
PLAQUE_OVERLAPS_A_CHAIR = """() => {
    const plaque = document.querySelector('.plaque').getBoundingClientRect();
    return [...document.querySelectorAll('.chair .tile, .chair .mark, .chair .bubble')].some((part) => {
        const box = part.getBoundingClientRect();
        return box.width > 0 && box.left < plaque.right && box.right > plaque.left
            && box.top < plaque.bottom && box.bottom > plaque.top;
    });
}"""
DEAL_ANIMATIONS = "[...document.querySelectorAll('.deal')].map((card) => getComputedStyle(card).animationName)"


@dataclass(frozen=True)
class Players:
    table_id: str
    path: str
    anna: Page
    ben: Page
    cleo: Page
    watcher: Page


def watch(person: Page, server: RunningServer, path: str) -> None:
    person.goto(f"{server.base_url}{path}")
    expect(person.locator(".chair")).to_have_count(3)


def sit_in(person: Page, seat: int) -> None:
    person.locator(f".chair[data-seat='{seat}']").get_by_role("button", name=SIT_DOWN).click()


def chair_of(person: Page, seat: int) -> Locator:
    return person.locator(f".chair[data-seat='{seat}']")


def stand_up_of(person: Page) -> Locator:
    return person.get_by_role("button", name=STAND_UP)


def table_with_two_seated(
    open_person: Callable[..., Page],
    server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> Players:
    def person(username: str, **options: Any) -> Page:
        return record_page_errors(open_person(username=username, **form_factor), page_errors, **options)

    anna = person("anna")
    path = open_new_table(anna, server)
    ben = person("ben", console=False)
    watch(ben, server, path)
    sit_in(ben, 2)
    expect(stand_up_of(ben)).to_be_visible()
    cleo = person("cleo")
    watcher = person("dora")
    for looker in (cleo, watcher):
        watch(looker, server, path)
    return Players(table_id_of(path), path, anna, ben, cleo, watcher)


def deal_the_hand(players: Players) -> None:
    sit_in(players.cleo, 3)
    for person in (players.anna, players.ben, players.cleo, players.watcher):
        wait_for_the_hand(person)


def wait_for_the_hand(person: Page) -> None:
    expect(person.locator(SKAT_CARD)).to_have_count(2)


def dealt_table(
    open_person: Callable[..., Page],
    server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> Players:
    players = table_with_two_seated(open_person, server, page_errors, form_factor)
    deal_the_hand(players)
    return players


def answer_of(person: Page, server: RunningServer, table_id: str) -> dict[str, Any]:
    return person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id}").json()


def drawn_table(person: Page) -> dict[str, Any]:
    return person.evaluate(DRAWN_TABLE)


def picture_of_answer(answer: dict[str, Any]) -> dict[str, Any]:
    """What the page must draw from the server's answer, for the viewer that answer belongs to."""
    return {
        "skat": answer["hand"]["skat_count"],
        "chairs": [
            {
                "seat": chair["seat"],
                "backs": 0 if chair["is_mine"] else chair["hand"]["card_count"],
                "count": None if chair["is_mine"] else str(chair["hand"]["card_count"]),
                "position": catalog_text(chair["hand"]["position"]),
                "dealer": DEALER if chair["seat"] == answer["hand"]["dealer_seat"] else None,
                "away": chair["is_away"],
            }
            for chair in sorted(answer["chairs"], key=lambda chair: chair["seat"])
        ],
    }


def page_and_answer_agree(person: Page, server: RunningServer, table_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Poll the drawn hand against a fresh answer until they are equal and nobody is away; fail with both on timeout."""
    deadline = time.monotonic() + USUAL_TIMEOUT_SECONDS
    while True:
        answer = answer_of(person, server, table_id)
        drawn = drawn_table(person)
        # A reloading player has no stream for a moment and shows away to the others; the snapshot waits for all four.
        settled = drawn == picture_of_answer(answer) and not any(chair["away"] for chair in drawn["chairs"])
        if settled or time.monotonic() >= deadline:
            assert drawn == picture_of_answer(answer)
            assert not any(chair["away"] for chair in drawn["chairs"])
            return answer, drawn
        person.wait_for_timeout(POLL_MILLISECONDS)


def assert_drawn_again(person: Page, drawn: dict[str, Any]) -> None:
    """Poll a reloaded page until it draws what it drew before; another player's reload can show away for a moment."""
    deadline = time.monotonic() + USUAL_TIMEOUT_SECONDS
    while drawn_table(person) != drawn and time.monotonic() < deadline:
        person.wait_for_timeout(POLL_MILLISECONDS)
    assert drawn_table(person) == drawn


def assert_no_horizontal_scroll(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def assert_plaque_is_clear_of_the_chairs(person: Page) -> None:
    assert person.evaluate(PLAQUE_OVERLAPS_A_CHAIR) is False


def assert_no_hand_is_drawn(person: Page) -> None:
    assert person.evaluate(EMPTY_CHAIRS) == 0


def write_dealer(server: RunningServer, table_id: str, seat: int) -> None:
    with server.engine.begin() as connection:
        connection.execute(update(tables).where(tables.c.id == table_id).values(dealer=seat))


def end_the_hand(server: RunningServer, table_id: str) -> None:
    with server.engine.begin() as connection:
        connection.execute(delete(hand_cards).where(hand_cards.c.table_id == table_id))
        connection.execute(update(tables).where(tables.c.id == table_id).values(dealer=None, last_played_at=None))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_viewer_sees_the_hand_as_the_server_answers_and_again_after_a_reload(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    players = dealt_table(open_person, e2e_server, page_errors, form_factor)

    for person in (players.anna, players.watcher):
        answer, drawn = page_and_answer_agree(person, e2e_server, players.table_id)
        assert {chair["backs"] for chair in drawn["chairs"] if not _is_mine(answer, chair["seat"])} == {10}
        assert drawn["skat"] == 2
        assert_no_horizontal_scroll(person)
        assert_plaque_is_clear_of_the_chairs(person)

        person.reload()
        wait_for_the_hand(person)

        assert_drawn_again(person, drawn)
    assert answer_of(players.watcher, e2e_server, players.table_id)["hand"]["own_cards"] == []


def _is_mine(answer: dict[str, Any], seat: int) -> bool:
    return next(chair["is_mine"] for chair in answer["chairs"] if chair["seat"] == seat)


def test_the_dealer_and_the_positions_follow_the_server_for_each_dealer(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    players = dealt_table(open_person, e2e_server, page_errors, DESKTOP)

    for dealer in (1, 2, 3):
        write_dealer(e2e_server, players.table_id, dealer)
        players.watcher.reload()
        wait_for_the_hand(players.watcher)

        answer = answer_of(players.watcher, e2e_server, players.table_id)
        drawn = drawn_table(players.watcher)
        assert answer["hand"]["dealer_seat"] == dealer
        assert drawn == picture_of_answer(answer)
        assert [chair["seat"] for chair in drawn["chairs"] if chair["dealer"] == DEALER] == [dealer]


def person_at(players: Players, server: RunningServer, position: str) -> Page:
    return next(
        person
        for person in (players.anna, players.ben, players.cleo)
        if any(
            chair["is_mine"] and chair["hand"]["position"] == position
            for chair in answer_of(person, server, players.table_id)["chairs"]
        )
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_auctions_bubbles_and_marks_stay_clear_of_the_plaque_for_every_viewer(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    players = dealt_table(open_person, e2e_server, page_errors, form_factor)
    everyone = (players.anna, players.ben, players.cleo, players.watcher)

    middlehand = person_at(players, e2e_server, "middlehand")
    middlehand.locator(MAIN_STEP).click()
    person_at(players, e2e_server, "forehand").locator(MAIN_STEP).click()

    expect(middlehand.locator(".mark.waits")).to_have_count(1)
    for person in everyone:
        expect(person.locator(".bubble")).to_have_count(2)
        expect(person.locator(".mark.turn")).to_have_count(1)
        assert_no_horizontal_scroll(person)
        assert_plaque_is_clear_of_the_chairs(person)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_no_stand_up_shows_while_a_hand_runs_and_it_returns_once_no_hand_runs(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    players = table_with_two_seated(open_person, e2e_server, page_errors, form_factor)
    expect(stand_up_of(players.anna)).to_be_visible()
    for person in (players.anna, players.watcher):
        assert_no_hand_is_drawn(person)

    deal_the_hand(players)

    expect(stand_up_of(players.anna)).to_have_count(0)
    expect(stand_up_of(players.ben)).to_have_count(0)

    end_the_hand(e2e_server, players.table_id)
    players.ben.reload()

    expect(stand_up_of(players.ben)).to_be_visible()
    assert_no_hand_is_drawn(players.ben)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_player_whose_stream_ends_shows_away_and_keeps_chair_and_cards(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    players = dealt_table(open_person, e2e_server, page_errors, form_factor)
    cleo_chair = chair_of(players.anna, 3)

    players.cleo.close()

    expect(cleo_chair.locator(".mark.away")).to_be_visible()
    expect(cleo_chair.locator(".plate")).to_contain_text("cleo")
    expect(cleo_chair.locator(".plate")).to_contain_text(SEAT_AWAY)
    expect(cleo_chair.locator(".fan.dim")).to_be_visible()
    answer = answer_of(players.anna, e2e_server, players.table_id)
    assert drawn_table(players.anna) == picture_of_answer(answer)
    assert_no_horizontal_scroll(players.anna)


def test_the_deal_animates_and_holds_still_for_reduced_motion(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    players = table_with_two_seated(open_person, e2e_server, page_errors, DESKTOP)
    still_person = record_page_errors(open_person(username="erik", reduced_motion="reduce", **DESKTOP), page_errors)
    watch(still_person, e2e_server, players.path)

    deal_the_hand(players)
    wait_for_the_hand(still_person)

    assert set(players.watcher.evaluate(DEAL_ANIMATIONS)) == {"deal"}
    assert set(still_person.evaluate(DEAL_ANIMATIONS)) == {"none"}


def test_a_stale_page_that_still_offers_stand_up_shows_the_refusal_once_a_hand_runs(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    players = table_with_two_seated(open_person, e2e_server, page_errors, DESKTOP)
    stale_view = json.dumps(answer_of(players.ben, e2e_server, players.table_id))

    def replay_the_view_before_the_hand(route: Route) -> None:
        route.fulfill(status=200, content_type="text/event-stream", body=f"data: {stale_view}\n\n")

    players.ben.route(f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}", replay_the_view_before_the_hand)
    players.ben.reload()
    expect(stand_up_of(players.ben)).to_be_visible()

    sit_in(players.cleo, 3)
    wait_for_the_hand(players.anna)
    expect(players.ben.locator(SKAT_CARD)).to_have_count(0)

    # The replayed stream keeps ending, so the stage is mostly dimmed for pointers; the click still has to count.
    stand_up_of(players.ben).dispatch_event("click")

    expect(players.ben.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    expect(chair_of(players.anna, 2).locator(".plate")).to_contain_text("ben")
