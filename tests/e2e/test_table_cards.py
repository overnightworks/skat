from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Response, expect

from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.tables import open_new_table

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
CARD_FACE = ".card-face"
HAND_CARD = ".own-hand .card"
WATCHER_COUNT = ".watchers span"
CARDS_IN_A_HAND = 10
SUITS = ("kreuz", "pik", "herz", "karo")
DISPLAY_ORDER = [(suit, "jack") for suit in SUITS] + [
    (suit, rank) for suit in SUITS for rank in ("ace", "ten", "king", "queen", "nine", "eight", "seven")
]
ANIMATIONS_OF_THE_HAND = """() => [...document.querySelectorAll('.own-hand .card')].flatMap(
    (card) => card.getAnimations().map((animation) => animation.playState)
)"""
HAND_HAS_SETTLED = f"() => ({ANIMATIONS_OF_THE_HAND})().every((state) => state === 'finished')"


def watch(person: Page, server: RunningServer, path: str) -> None:
    person.goto(f"{server.base_url}{path}")
    expect(person.locator(".chair")).to_have_count(3)


def sit_in(person: Page, seat: int) -> None:
    person.locator(f".chair[data-seat='{seat}']").get_by_role("button", name=SIT_DOWN).click()


def note_of(person: Page) -> Locator:
    return person.locator(".plaque")


def card_faces_of(person: Page) -> Locator:
    return person.locator(CARD_FACE)


def drawn_cards_of(person: Page) -> list[tuple[str, str]]:
    drawn = card_faces_of(person).evaluate_all("(faces) => faces.map((face) => [face.dataset.suit, face.dataset.rank])")
    return [(suit, rank) for suit, rank in drawn]


def answer_cards_in_display_order(answer: dict[str, Any]) -> list[tuple[str, str]]:
    held = {(card["suit"], card["rank"]) for card in answer["hand"]["own_cards"]}
    return [card for card in DISPLAY_ORDER if card in held]


def assert_whole_hand_inside_the_viewport(person: Page) -> None:
    viewport = person.viewport_size
    assert viewport is not None
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    for card in person.locator(HAND_CARD).all():
        box = card.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["y"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]
        assert box["y"] + box["height"] <= viewport["height"]


def is_table_answer(response: Response, table_path: str) -> bool:
    return response.url.endswith(table_path) and response.request.method == "GET"


def reload_and_read_the_answer(person: Page, table_path: str) -> dict[str, Any]:
    with person.expect_response(lambda response: is_table_answer(response, table_path)) as answer:
        person.reload()
    return answer.value.json()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_each_seated_player_sees_their_own_ten_cards_after_the_deal_and_a_reload(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    second = record_page_errors(open_person(username="ben", **form_factor), page_errors)
    watch(second, e2e_server, path)
    sit_in(second, 2)
    third = record_page_errors(open_person(username="cleo", **form_factor), page_errors)
    watch(third, e2e_server, path)
    table_path = f"{TABLES_PATH}/{path.rsplit('/', 1)[-1]}"
    players = (opener, second, third)

    for person in (opener, second):
        expect(note_of(person)).to_have_text(WAITING_FOR_PLAYERS)
        expect(card_faces_of(person)).to_have_count(0)

    sit_in(third, 3)

    for person in players:
        expect(card_faces_of(person)).to_have_count(CARDS_IN_A_HAND)
        expect(note_of(person)).to_have_text(BIDDING)
        person.wait_for_function(HAND_HAS_SETTLED)
        assert_whole_hand_inside_the_viewport(person)
    for person in players:
        cards_before_the_reload = drawn_cards_of(person)

        answer = reload_and_read_the_answer(person, table_path)

        expect(card_faces_of(person)).to_have_count(CARDS_IN_A_HAND)
        person.wait_for_function(HAND_HAS_SETTLED)
        assert cards_before_the_reload == answer_cards_in_display_order(answer)
        assert drawn_cards_of(person) == cards_before_the_reload
        assert_whole_hand_inside_the_viewport(person)


def test_a_watcher_sees_no_card_and_a_stream_message_leaves_a_players_hand_as_it_is(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    for seat, username in ((2, "ben"), (3, "cleo")):
        sitter = record_page_errors(open_person(username=username, **DESKTOP), page_errors)
        watch(sitter, e2e_server, path)
        sit_in(sitter, seat)
    expect(card_faces_of(opener)).to_have_count(CARDS_IN_A_HAND)
    opener.wait_for_function(HAND_HAS_SETTLED)
    cards_before_the_message = drawn_cards_of(opener)
    first_card = opener.locator(HAND_CARD).first
    first_card.evaluate("(card) => { card.dataset.keptAcrossMessages = 'yes'; }")

    watcher = record_page_errors(open_person(username="dora", **DESKTOP), page_errors)
    watch(watcher, e2e_server, path)

    expect(watcher.locator(WATCHER_COUNT)).to_have_text("1")
    expect(opener.locator(WATCHER_COUNT)).to_have_text("1")
    expect(note_of(watcher)).to_have_text(BIDDING)
    expect(card_faces_of(watcher)).to_have_count(0)
    expect(first_card).to_have_attribute("data-kept-across-messages", "yes")
    assert drawn_cards_of(opener) == cards_before_the_message
    assert "running" not in opener.evaluate(ANIMATIONS_OF_THE_HAND)


@pytest.mark.parametrize(("reduced_motion", "animates"), [("no-preference", True), ("reduce", False)])
def test_the_deal_animates_unless_the_player_prefers_reduced_motion(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    reduced_motion: str,
    animates: bool,
) -> None:
    opener = record_page_errors(open_person(username="anna", reduced_motion=reduced_motion, **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    for seat, username in ((2, "ben"), (3, "cleo")):
        sitter = record_page_errors(open_person(username=username, **DESKTOP), page_errors)
        watch(sitter, e2e_server, path)
        sit_in(sitter, seat)

    expect(card_faces_of(opener)).to_have_count(CARDS_IN_A_HAND)

    assert bool(opener.evaluate(ANIMATIONS_OF_THE_HAND)) is animates
