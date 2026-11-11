import json
import re
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.table.auction import AuctionAction
from skat.web.auction import (
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
)
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of, watch
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
BIDDING = catalog_text("bidding")
HOLD = catalog_text("hold")
COMMAND_FAILED = catalog_text("commandFailed")
WAITING_FOR_PLAYERS = catalog_text("waitingForPlayers")
PASS = catalog_text("pass")
WAITING_FOR = catalog_text("waitingFor")
WAITS_FOR_YOU = catalog_text("waitsForYou")
PASSED_IN = catalog_text("passedIn")
GIVES = catalog_text("gives")
YOU = catalog_text("sideYou")
LOWEST_BID = 18
SKAT_CARD = ".skat-card"
LADDER = ".ladder"
HELD = ".ladder .held"
LIT = ".ladder .now"
HIGHER = ".ladder .higher button"
MAIN = ".bid-buttons .button-stage"
STRIP = ".ladder .higher"
TURN_CHAIR = ".chair.mine.turn"
PLAQUE = ".plaque"
CARD_FACE = ".card-face"
BUBBLE = ".bubble"
VERDICT = ".plaque .verdict"
GIVES_LINE = ".plaque .gives"
DEALER_MARK = ".mark.dealer"
DECK = ".deck"
OUT = re.compile(r"\bout\b")
TOP_BID = "264"
FIRST_HIGHER_BID = "20"
HIGHER_BID_TAPPED = "30"
BID_TO_ANSWER = 20
NOT_OBSCURED_BY_THE_STRIP = """(button) => {
    const strip = button.closest('.higher').getBoundingClientRect();
    const box = button.getBoundingClientRect();
    return box.left >= strip.left - 1 && box.right <= strip.right + 1;
}"""


@dataclass(frozen=True)
class Table:
    server: RunningServer
    id: str
    forehand: Page
    middlehand: Page
    rearhand: Page
    watcher: Page

    @property
    def everyone(self) -> tuple[Page, ...]:
        return (self.forehand, self.middlehand, self.rearhand, self.watcher)


@dataclass(frozen=True)
class Marks:
    """What one chair carries on one screen during the auction; the fields are this test's own."""

    bubble: str | None = None
    quiet: bool = False
    passed: bool = False
    turn: bool = False
    waits: bool = False


@dataclass(frozen=True)
class Scene:
    """The marks every viewer sees, and the one screen that shows a chair waiting on its viewer."""

    forehand: Marks
    middlehand: Marks
    rearhand: Marks
    waits: tuple[str, str] | None

    def seen_by(self, viewer: str) -> dict[str, Marks]:
        chairs = {"forehand": self.forehand, "middlehand": self.middlehand, "rearhand": self.rearhand}
        if self.waits is not None and self.waits[0] == viewer:
            chairs[self.waits[1]] = replace(chairs[self.waits[1]], waits=True)
        return chairs


def answer_of(person: Page, table: Table) -> dict[str, Any]:
    return person.request.get(f"{table.server.base_url}{TABLES_PATH}/{table.id}").json()


def position_of(person: Page, server: RunningServer, table_id: str) -> str:
    answer = person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id}").json()
    return next(chair["hand"]["position"] for chair in answer["chairs"] if chair["is_mine"])


def dealt_table(
    open_person: Callable[..., Page],
    server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    *,
    console: bool = True,
) -> Table:
    def person(username: str) -> Page:
        return record_page_errors(open_person(username=username, **form_factor), page_errors, console=console)

    anna = person("anna")
    path = open_new_table(anna, server)
    ben, cleo, dora = person("ben"), person("cleo"), person("dora")
    for looker in (ben, cleo, dora):
        watch(looker, server, path)
    sit_in(ben, 2)
    expect(ben.locator(".chair[data-seat='2'] .plate")).to_contain_text(YOU)
    sit_in(cleo, 3)
    for looker in (anna, ben, cleo, dora):
        expect(looker.locator(SKAT_CARD)).to_have_count(2)
    table_id = table_id_of(path)
    by_position = {position_of(player, server, table_id): player for player in (anna, ben, cleo)}
    return Table(server, table_id, by_position["forehand"], by_position["middlehand"], by_position["rearhand"], dora)


STEP_SUFFIXES = {
    AuctionAction.BID: TABLE_AUCTION_BID_SUFFIX,
    AuctionAction.HOLD: TABLE_AUCTION_HOLD_SUFFIX,
    AuctionAction.PASS: TABLE_AUCTION_PASS_SUFFIX,
    AuctionAction.PLAY: TABLE_AUCTION_PLAY_SUFFIX,
}


def step(person: Page, table: Table, action: AuctionAction, value: int | None = None) -> None:
    """A step taken behind the page, as the player's other device would."""
    payload: dict[str, Any] = {
        "command_id": uuid.uuid4().hex,
        "version": answer_of(person, table)["version"],
    }
    if value is not None:
        payload["value"] = value
    response = person.request.post(
        f"{table.server.base_url}{TABLES_PATH}/{table.id}{STEP_SUFFIXES[action]}",
        data=payload,
        headers={"Origin": table.server.base_url},
    )
    assert response.ok, response.text()


def own_word(person: Page, table: Table) -> tuple[str, int | None]:
    """`person`'s last word in the auction, from their own answer."""
    answer = answer_of(person, table)
    seat = next(chair["seat"] for chair in answer["chairs"] if chair["is_mine"])
    word = next(word for word in answer["hand"]["auction"]["words"] if word["seat"] == seat)
    return word["action"], word["value"]


def assert_no_controls(person: Page) -> None:
    expect(person.locator(LADDER)).to_have_count(0)
    expect(person.get_by_role("button", name=PASS)).to_have_count(0)


def assert_page_fits(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def assert_the_opening_ladder(person: Page) -> None:
    expect(person.locator(HELD)).to_have_count(0)
    expect(person.locator(LIT)).to_have_text(str(LOWEST_BID))
    expect(person.locator(MAIN)).to_have_text(str(LOWEST_BID))
    expect(person.get_by_role("button", name=PASS)).to_be_visible()
    expect(person.locator(HIGHER).first).to_have_text(FIRST_HIGHER_BID)
    expect(person.locator(HIGHER).last).to_have_text(TOP_BID)
    assert_page_fits(person)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_middlehand_opens_and_only_the_one_whose_turn_it_is_gets_controls(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand

    assert_the_opening_ladder(middlehand)
    expect(middlehand.locator(TURN_CHAIR)).to_have_count(1)
    for other in (table.forehand, table.rearhand, table.watcher):
        expect(other.locator(PLAQUE)).to_have_text(BIDDING)
        assert_no_controls(other)
        expect(other.locator(TURN_CHAIR)).to_have_count(0)

    middlehand.reload()
    assert_the_opening_ladder(middlehand)

    middlehand.locator(MAIN).click()

    expect(table.forehand.get_by_role("button", name=HOLD)).to_be_visible()
    assert_no_controls(middlehand)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, LOWEST_BID)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_forehand_answers_a_bid_and_the_bidder_climbs_on(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.BID, BID_TO_ANSWER)
    forehand = table.forehand

    expect(forehand.locator(LIT)).to_have_text(str(BID_TO_ANSWER))
    expect(forehand.locator(HELD)).to_have_count(0)
    assert forehand.locator(".ladder > span").all_inner_texts()[1:] == ["22", "23", "24"]
    expect(forehand.locator(HIGHER)).to_have_count(0)
    expect(forehand.locator(MAIN)).to_have_text(HOLD)
    expect(forehand.get_by_role("button", name=PASS)).to_be_visible()
    assert_page_fits(forehand)

    forehand.reload()
    expect(forehand.locator(MAIN)).to_have_text(HOLD)

    forehand.locator(MAIN).click()

    expect(table.middlehand.locator(LIT)).to_have_text("22")
    expect(table.middlehand.locator(HELD)).to_have_text(str(BID_TO_ANSWER))
    assert_no_controls(forehand)
    assert own_word(forehand, table) == (AuctionAction.HOLD.value, BID_TO_ANSWER)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_on_a_higher_value_bids_that_value_at_once(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)

    table.middlehand.locator(STRIP).get_by_role("button", name=HIGHER_BID_TAPPED, exact=True).click()

    expect(table.forehand.locator(LIT)).to_have_text(HIGHER_BID_TAPPED)
    assert own_word(table.middlehand, table) == (AuctionAction.BID.value, int(HIGHER_BID_TAPPED))


def test_a_mouse_scrolls_the_strip_to_the_top_value_and_clicks_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, DESKTOP)
    middlehand = table.middlehand
    strip = middlehand.locator(STRIP)
    assert strip.evaluate("(strip) => getComputedStyle(strip).scrollbarWidth") == "thin"
    assert strip.evaluate("(strip) => strip.scrollLeft") == 0

    box = strip.bounding_box()
    middlehand.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    middlehand.mouse.wheel(10_000, 0)
    middlehand.wait_for_function(
        "() => { const strip = document.querySelector('.higher');"
        " return strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 1; }"
    )
    top = middlehand.locator(HIGHER).last
    expect(top).to_have_text(TOP_BID)
    place = top.bounding_box()
    middlehand.mouse.click(place["x"] + place["width"] / 2, place["y"] + place["height"] / 2)

    expect(table.forehand.locator(LIT)).to_have_text(TOP_BID)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, int(TOP_BID))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_keyboard_walks_the_strip_and_enter_bids_the_focused_value(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand
    values = middlehand.locator(HIGHER)
    expect(values.first).to_be_visible()
    last_index = values.count() - 1

    values.first.focus()
    for index in range(last_index + 1):
        expect(values.nth(index)).to_be_focused()
        assert values.nth(index).evaluate(NOT_OBSCURED_BY_THE_STRIP) is True
        if index < last_index:
            middlehand.keyboard.press("Tab")
    middlehand.keyboard.press("Enter")

    expect(table.forehand.locator(LIT)).to_have_text(TOP_BID)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, int(TOP_BID))


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize("awaiting", ["bid", "answer", "play"])
def test_a_tap_on_weg_counts_at_once_at_any_own_turn(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    awaiting: str,
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    if awaiting == "bid":
        tapper = table.middlehand
    elif awaiting == "answer":
        step(table.middlehand, table, AuctionAction.BID, LOWEST_BID)
        tapper = table.forehand
    else:
        step(table.middlehand, table, AuctionAction.PASS)
        step(table.rearhand, table, AuctionAction.PASS)
        tapper = table.forehand

    tapper.get_by_role("button", name=PASS).click()

    assert_no_controls(tapper)
    if awaiting == "play":
        assert answer_of(tapper, table)["hand"] is None
        assert answer_of(tapper, table)["passed_in"] is not None
    else:
        assert own_word(tapper, table) == (AuctionAction.PASS.value, None)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_forehand_plays_at_18_after_two_passes(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.PASS)
    step(table.rearhand, table, AuctionAction.PASS)
    forehand = table.forehand

    expect(forehand.locator(LIT)).to_have_text(str(LOWEST_BID))
    expect(forehand.locator(HELD)).to_have_count(0)
    assert forehand.locator(".ladder > span").all_inner_texts()[1:] == []
    expect(forehand.locator(MAIN)).to_have_text(str(LOWEST_BID))
    assert_page_fits(forehand)

    forehand.locator(MAIN).click()

    assert_no_controls(forehand)
    assert own_word(forehand, table) == (AuctionAction.PLAY.value, LOWEST_BID)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_at_the_top_of_the_ladder_only_weg_shows(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.BID, int(TOP_BID))
    step(table.forehand, table, AuctionAction.HOLD)
    middlehand = table.middlehand

    expect(middlehand.get_by_role("button", name=PASS)).to_be_visible()
    expect(middlehand.locator(LADDER)).to_have_count(0)
    expect(middlehand.locator(MAIN)).to_have_count(0)
    assert_page_fits(middlehand)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_double_tap_takes_exactly_one_step(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand
    steps_sent: list[str] = []
    middlehand.on(
        "request",
        lambda request: (
            steps_sent.append(request.url)
            if request.method == "POST" and request.url.endswith(tuple(STEP_SUFFIXES.values()))
            else None
        ),
    )

    middlehand.locator(MAIN).dblclick()

    expect(table.forehand.locator(LIT)).to_have_text(str(LOWEST_BID))
    assert_no_controls(middlehand)
    assert len(steps_sent) == 1
    assert own_word(middlehand, table) == (AuctionAction.BID.value, LOWEST_BID)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_step_from_a_stale_page_shows_the_refusal_and_the_stream_corrects_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor, console=False)
    middlehand = table.middlehand
    stale_view = json.dumps(answer_of(middlehand, table))

    def replay_the_view_before_the_step(route: Route) -> None:
        route.fulfill(status=200, content_type="text/event-stream", body=f"data: {stale_view}\n\n")

    events = f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}"
    middlehand.route(events, replay_the_view_before_the_step)
    middlehand.reload()
    expect(middlehand.locator(MAIN)).to_be_visible()
    step(middlehand, table, AuctionAction.BID, LOWEST_BID)

    # The replayed stream keeps ending, so the stage is dimmed for pointers; the click still has to count.
    middlehand.locator(MAIN).dispatch_event("click")

    expect(middlehand.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    expect(middlehand.locator(MAIN)).to_be_enabled()

    middlehand.unroute(events)

    assert_no_controls(middlehand)


def test_no_controls_and_no_auction_word_before_a_hand(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    anna = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    open_new_table(anna, e2e_server)

    expect(anna.locator(PLAQUE)).to_have_text(WAITING_FOR_PLAYERS)
    expect(anna.get_by_text(BIDDING)).to_have_count(0)
    assert_no_controls(anna)


@pytest.mark.parametrize(("motion", "animated"), [("no-preference", True), ("reduce", False)])
def test_the_own_turn_ring_breathes_and_holds_still_for_reduced_motion(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], motion: str, animated: bool
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, {**DESKTOP, "reduced_motion": motion})

    expect(table.middlehand.locator(TURN_CHAIR)).to_have_count(1)
    tile = table.middlehand.locator(f"{TURN_CHAIR} .tile")
    assert ("breathe" in tile.evaluate("(tile) => getComputedStyle(tile).animationName")) is animated


def seats_by_position(table: Table) -> dict[str, int]:
    answer = answer_of(table.watcher, table)
    return {chair["hand"]["position"]: chair["seat"] for chair in answer["chairs"]}


def viewers(table: Table) -> dict[str, Page]:
    return {
        "forehand": table.forehand,
        "middlehand": table.middlehand,
        "rearhand": table.rearhand,
        "watcher": table.watcher,
    }


def assert_chair(person: Page, seat: int, marks: Marks) -> None:
    chair = person.locator(f".chair[data-seat='{seat}']")
    expect(chair.locator(".mark.turn")).to_have_count(int(marks.turn))
    if marks.bubble is None:
        expect(chair.locator(BUBBLE)).to_have_count(0)
    else:
        expect(chair.locator(f"{BUBBLE} .said")).to_have_text(marks.bubble)
    expect(chair.locator(".bubble.quiet svg")).to_have_count(int(marks.quiet))
    expect(chair.locator(".mark.pass")).to_have_count(int(marks.passed))
    if marks.passed:
        expect(chair).to_have_class(OUT)
        expect(chair.locator(".mark.pass")).to_contain_text(PASS)
    else:
        expect(chair).not_to_have_class(OUT)
    expect(chair.locator(".mark.waits")).to_have_count(int(marks.waits))
    if marks.waits:
        expect(chair.locator(".mark.waits")).to_have_attribute("title", WAITS_FOR_YOU)


def assert_scene(table: Table, scene: Scene) -> None:
    seats = seats_by_position(table)
    for viewer, person in viewers(table).items():
        chairs = scene.seen_by(viewer)
        # The chair on turn comes first: its mark waits until the stream has brought the step.
        for position, marks in sorted(chairs.items(), key=lambda chair: not chair[1].turn):
            assert_chair(person, seats[position], marks)
        expect(person.locator(".chair.turn")).to_have_count(1)
        assert_page_fits(person)
    expect(table.watcher.locator(CARD_FACE)).to_have_count(0)


BIDDER = Marks(bubble=str(LOWEST_BID))
HOLDER = Marks(bubble=str(LOWEST_BID), quiet=True)
PASSED = Marks(passed=True)
ON_TURN = Marks(turn=True)
SILENT = Marks()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_viewer_sees_each_chairs_last_word_whose_turn_it_is_and_who_waits_on_whom(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    script: list[tuple[Page | None, AuctionAction | None, Scene]] = [
        (None, None, Scene(SILENT, ON_TURN, SILENT, waits=("middlehand", "forehand"))),
        (
            table.middlehand,
            AuctionAction.BID,
            Scene(ON_TURN, BIDDER, SILENT, waits=("forehand", "middlehand")),
        ),
        (
            table.forehand,
            AuctionAction.HOLD,
            Scene(HOLDER, replace(BIDDER, turn=True), SILENT, waits=("middlehand", "forehand")),
        ),
        (
            table.middlehand,
            AuctionAction.PASS,
            Scene(HOLDER, PASSED, ON_TURN, waits=("rearhand", "forehand")),
        ),
    ]

    for person, action, scene in script:
        if person is not None and action is not None:
            step(person, table, action, LOWEST_BID if action is AuctionAction.BID else None)
        assert_scene(table, scene)

    for person in table.everyone:
        person.reload()
    assert_scene(table, script[-1][2])


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_after_two_passes_the_forehand_takes_18_with_nobody_waiting_and_two_chairs_out(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)

    step(table.middlehand, table, AuctionAction.PASS)
    step(table.rearhand, table, AuctionAction.PASS)

    assert_scene(table, Scene(ON_TURN, PASSED, PASSED, waits=None))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_plaque_waits_for_the_player_on_turn_while_they_are_away(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand
    name = next(chair["occupant_name"] for chair in answer_of(middlehand, table)["chairs"] if chair["is_mine"])
    others = (table.forehand, table.rearhand, table.watcher)

    returning = record_page_errors(middlehand.context.new_page(), page_errors)
    middlehand.close()

    for person in others:
        expect(person.locator(PLAQUE)).to_have_text(f"{WAITING_FOR} {name}")
        assert_page_fits(person)

    watch(returning, table.server, f"{TABLE_PAGE_PREFIX}{table.id}")

    for person in (*others, returning):
        expect(person.locator(PLAQUE)).to_have_text(BIDDING)


def passed_in_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> Table:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.PASS)
    step(table.rearhand, table, AuctionAction.PASS)
    step(table.forehand, table, AuctionAction.PASS)
    return table


def next_dealer(table: Table) -> tuple[int, str]:
    answer = answer_of(table.watcher, table)
    seat = answer["passed_in"]["next_dealer_seat"]
    return seat, next(chair["occupant_name"] for chair in answer["chairs"] if chair["seat"] == seat)


def assert_the_hand_is_passed_in(person: Page, dealer: tuple[int, str] | None) -> None:
    expect(person.locator(VERDICT)).to_have_text(PASSED_IN)
    expect(person.locator(DECK)).to_have_count(1)
    expect(person.locator(".chair .mark.pass")).to_have_count(3)
    expect(person.locator(".chair.out")).to_have_count(3)
    if dealer is None:
        expect(person.locator(GIVES_LINE)).to_have_count(0)
        expect(person.locator(DEALER_MARK)).to_have_count(0)
    else:
        seat, name = dealer
        expect(person.locator(GIVES_LINE)).to_have_text(f"{name} {GIVES}")
        expect(person.locator(DEALER_MARK)).to_have_count(1)
        expect(person.locator(f".chair[data-seat='{seat}'] {DEALER_MARK}")).to_have_count(1)
    assert_page_fits(person)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_after_three_passes_every_viewer_sees_eingepasst_and_the_next_dealer_then_the_new_hand(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = passed_in_table(open_person, e2e_server, page_errors, form_factor)
    dealer = next_dealer(table)

    for person in table.everyone:
        assert_the_hand_is_passed_in(person, dealer)
    table.watcher.reload()
    assert_the_hand_is_passed_in(table.watcher, dealer)

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_have_text(BIDDING)
        expect(person.locator(DECK)).to_have_count(0)
        expect(person.locator(SKAT_CARD)).to_have_count(2)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_while_a_member_is_away_eingepasst_stays_without_a_dealer_until_they_return(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.PASS)
    step(table.rearhand, table, AuctionAction.PASS)
    returning = record_page_errors(table.rearhand.context.new_page(), page_errors)
    away_seat = next(chair["seat"] for chair in answer_of(table.rearhand, table)["chairs"] if chair["is_mine"])
    table.rearhand.close()
    present = (table.forehand, table.middlehand, table.watcher)
    for person in present:
        expect(person.locator(f".chair[data-seat='{away_seat}'].away")).to_have_count(1)

    step(table.forehand, table, AuctionAction.PASS)

    for person in present:
        assert_the_hand_is_passed_in(person, None)
        expect(person.locator(f".chair[data-seat='{away_seat}'].away .mark.pass")).to_have_count(1)

    watch(returning, table.server, f"{TABLE_PAGE_PREFIX}{table.id}")

    dealer = next_dealer(table)
    for person in (*present, returning):
        expect(person.locator(GIVES_LINE)).to_have_text(f"{dealer[1]} {GIVES}")
    for person in (*present, returning):
        expect(person.locator(PLAQUE)).to_have_text(BIDDING)
