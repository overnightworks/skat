import json
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.engine.bidding import VALID_BIDS
from skat.table.auction import AuctionAction
from skat.table.records import PlanMode, TableStyle
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH, PlanKind
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.audio import (
    CONFIRMATIONS,
    RECORDING_COUNT,
    keys_said,
    tap,
    wait_for_recordings_decoded,
    wait_for_recordings_started,
)
from tests.e2e.support.bidding import (
    BAR,
    CHIPS,
    LIMIT_VALUE,
    MORE,
    PASS,
    PASS_KEY,
    SKAT_CARD,
    STEP_KEY,
    STEP_SUFFIXES,
    BiddingTable,
    answer_of,
    assert_no_controls,
    assert_page_fits,
    chip,
    dealt_table,
    first_bid_above,
    limit_at,
    own_plan,
    own_values,
    own_word,
    pass_key,
    plan_ahead,
    step,
)
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.style import STYLES, expect_painted_as_the_scene, expect_the_furniture_clear
from tests.e2e.support.tables import open_new_table, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.deal_pause import HeldDealPause
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
HOLD = text(SOURCE_LANGUAGE, "bid.hold")
ASK = text(SOURCE_LANGUAGE, "bid.ask")
FIXED = text(SOURCE_LANGUAGE, "bid.fixed")
ASKED = text(SOURCE_LANGUAGE, "bid.asked")
PASS_AHEAD = text(SOURCE_LANGUAGE, "bid.passAhead")
TAKEN_BACK = text(SOURCE_LANGUAGE, "bid.takenBack")
CLEAR_LIMIT = text(SOURCE_LANGUAGE, "bid.clearLimit")
LIMIT_CLEARED = text(SOURCE_LANGUAGE, "bid.limitCleared")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
WAITS_FOR_YOU = text(SOURCE_LANGUAGE, "table.waitsForYou")
PASSED_IN = text(SOURCE_LANGUAGE, "table.passedIn")
LOWEST_BID, SECOND_BID, THIRD_BID, *_, TOP_BID = VALID_BIDS
PAINT = ["backgroundColor", "color"]
# What the table says for a bidder up to the third value against a responder who holds up to the second: three bids,
# two holds and the responder's pass.
WORDS_OF_THE_RUN = 6
ASKS = ".bid-line .asks"
PLAN_LINE = ".bid-line"
PLAN_NOTE = f"{PLAN_LINE} .said"
PASSED_LINE = f"{PLAN_LINE}.dim"
PLACE_AND_OPACITY = "(line) => [Math.round(line.getBoundingClientRect().top), Number(getComputedStyle(line).opacity)]"
TURN_CHAIR = ".chair.mine.turn"
FAR_TURN_CHAIR = ".chair.turn:not(.mine)"
PLAQUE = ".plaque"
COUNTER_WORD = ".counter .word"
CARD_FACE = ".card-face"
BUBBLE = ".bubble"
VERDICT = ".plaque .verdict"
GIVES_LINE = ".plaque .gives"
DEALER_MARK = ".mark.dealer"
DECK = ".deck"
OUT = re.compile(r"\bout\b")


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


def assert_the_chips(person: Page, table: BiddingTable) -> None:
    expect(pass_key(person)).to_be_visible()
    expect(person.locator(CHIPS)).to_have_text([str(value) for value in own_values(person, table)])
    expect(person.locator(MORE)).to_be_visible()
    assert_page_fits(person)


def assert_the_opening_bar(person: Page, table: BiddingTable) -> None:
    expect(person.locator(STEP_KEY)).to_have_text(str(LOWEST_BID))
    assert_the_chips(person, table)


@pytest.mark.parametrize("table_style", STYLES)
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_middlehand_opens_and_only_the_one_whose_turn_it_is_gets_the_key_that_says_the_next_word(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    table_style: TableStyle,
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor, style=table_style)
    middlehand = table.middlehand

    assert_the_opening_bar(middlehand, table)
    expect_the_furniture_clear(table.everyone, table_style)
    if table_style is TableStyle.STRANDBAR:
        expect_painted_as_the_scene(middlehand, "strand-auction", PASS_KEY, ".btns .button-glass", PAINT)
        expect_painted_as_the_scene(middlehand, "strand-auction", CHIPS, ".bid-chip", PAINT)
    expect(middlehand.locator(TURN_CHAIR)).to_have_count(1)
    for other in (table.forehand, table.rearhand):
        expect(other.locator(COUNTER_WORD)).to_have_text(BIDDING)
        assert_the_chips(other, table)
        expect(other.locator(STEP_KEY)).to_have_count(0)
        expect(other.locator(TURN_CHAIR)).to_have_count(0)
    expect(table.watcher.locator(COUNTER_WORD)).to_have_text(BIDDING)
    assert_no_controls(table.watcher)

    chip(table.rearhand, own_values(table.rearhand, table)[-1]).click()

    expect(table.rearhand.get_by_role("button", name=CLEAR_LIMIT)).to_be_visible()
    expect_the_furniture_clear([table.rearhand], table_style)

    middlehand.reload()
    assert_the_opening_bar(middlehand, table)

    middlehand.locator(STEP_KEY).click()

    expect(table.forehand.locator(STEP_KEY)).to_have_text(HOLD)
    expect(middlehand.locator(STEP_KEY)).to_have_count(0)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, LOWEST_BID)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_forehand_answers_a_bid_and_the_bidder_climbs_on(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.BID, SECOND_BID)
    forehand = table.forehand

    expect(forehand.locator(STEP_KEY)).to_have_text(HOLD)
    assert_the_chips(forehand, table)

    forehand.reload()
    expect(forehand.locator(STEP_KEY)).to_have_text(HOLD)

    forehand.locator(STEP_KEY).click()

    expect(table.middlehand.locator(STEP_KEY)).to_have_text(str(THIRD_BID))
    expect(forehand.locator(STEP_KEY)).to_have_count(0)
    assert own_word(forehand, table) == (AuctionAction.HOLD.value, SECOND_BID)


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
    expect(tapper.locator(STEP_KEY)).to_be_visible()

    pass_key(tapper).click()

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

    assert_the_opening_bar(forehand, table)

    forehand.locator(STEP_KEY).click()

    assert_no_controls(forehand)
    assert own_word(forehand, table) == (AuctionAction.PLAY.value, LOWEST_BID)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_at_the_top_of_the_ladder_no_key_says_a_higher_word(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.BID, TOP_BID)
    step(table.forehand, table, AuctionAction.HOLD)
    middlehand = table.middlehand

    expect(pass_key(middlehand)).to_be_visible()
    expect(middlehand.locator(STEP_KEY)).to_have_count(0)
    expect(middlehand.locator(f"{CHIPS}:enabled")).to_have_count(0)
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

    middlehand.locator(STEP_KEY).dblclick()

    expect(table.forehand.locator(STEP_KEY)).to_have_text(HOLD)
    expect(middlehand.locator(STEP_KEY)).to_have_count(0)
    assert len(steps_sent) == 1
    assert own_word(middlehand, table) == (AuctionAction.BID.value, LOWEST_BID)


def with_a_view_that_stays_as_it_is(person: Page, table: BiddingTable) -> str:
    """`person`'s page stops hearing the table: its stream replays the view of now; the pattern ends the replay."""
    stale_view = json.dumps(answer_of(person, table))

    def replay_the_view(route: Route) -> None:
        route.fulfill(status=200, content_type="text/event-stream", body=f"data: {stale_view}\n\n")

    events = f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}"
    person.route(events, replay_the_view)
    person.reload()
    expect(pass_key(person)).to_be_visible()
    return events


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_step_from_a_stale_page_shows_the_refusal_and_the_stream_corrects_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor, console=False)
    middlehand = table.middlehand
    events = with_a_view_that_stays_as_it_is(middlehand, table)
    step(middlehand, table, AuctionAction.BID, LOWEST_BID)

    # The replayed stream keeps ending, so the stage is dimmed for pointers; the click still has to count.
    middlehand.locator(STEP_KEY).dispatch_event("click")

    expect(middlehand.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    expect(middlehand.locator(STEP_KEY)).to_be_enabled()

    middlehand.unroute(events)

    expect(middlehand.locator(STEP_KEY)).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_limit_the_auction_has_passed_shows_the_refusal_and_the_stream_corrects_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor, console=False)
    rearhand = table.rearhand
    lowest = own_values(rearhand, table)[0]
    events = with_a_view_that_stays_as_it_is(rearhand, table)
    step(table.middlehand, table, AuctionAction.BID, first_bid_above(lowest))

    chip(rearhand, lowest).dispatch_event("click")

    expect(rearhand.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    assert own_plan(rearhand, table) is None

    rearhand.unroute(events)

    expect(chip(rearhand, lowest)).to_be_disabled()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_limit_holds_for_its_owner_and_above_it_the_table_asks_him(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    forehand, middlehand = table.forehand, table.middlehand
    limit = own_values(forehand, table)[-1]

    chip(forehand, limit).click()

    expect(chip(forehand, limit)).to_have_attribute("aria-pressed", "true")
    expect(forehand.locator(LIMIT_VALUE)).to_have_text(str(limit))
    expect(forehand.get_by_role("button", name=ASK, exact=True)).to_have_attribute("aria-pressed", "true")
    assert own_plan(forehand, table) == limit_at(limit, PlanMode.ASK)
    assert_page_fits(forehand)

    middlehand.locator(STEP_KEY).click()

    expect(middlehand.locator(STEP_KEY)).to_have_text(str(SECOND_BID))
    assert_scene(table, Scene(HOLDER, replace(BIDDER, turn=True), SILENT, waits=("middlehand", "forehand")))
    assert own_word(forehand, table) == (AuctionAction.HOLD.value, LOWEST_BID)

    above = first_bid_above(limit)
    step(middlehand, table, AuctionAction.BID, above)

    expect(forehand.locator(ASKS)).to_contain_text(ASKED)
    expect(forehand.locator(f"{ASKS} b")).to_have_text(str(limit))
    expect(forehand.locator(STEP_KEY)).to_have_text(HOLD)
    assert own_word(forehand, table) == (AuctionAction.HOLD.value, LOWEST_BID)
    assert_page_fits(forehand)

    forehand.locator(STEP_KEY).click()

    expect(middlehand.locator(STEP_KEY)).to_be_visible()
    assert own_word(forehand, table) == (AuctionAction.HOLD.value, above)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_limit_moved_to_another_chip_stays_fixed_and_above_it_the_table_passes_and_leaves_it_dimmed(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    forehand = table.forehand
    lowest, *_, highest = own_values(forehand, table)
    chip(forehand, highest).click()

    fixed = forehand.get_by_role("button", name=FIXED, exact=True)

    fixed.click()

    expect(fixed).to_have_attribute("aria-pressed", "true")
    assert own_plan(forehand, table) == limit_at(highest, PlanMode.FIXED)

    chip(forehand, lowest).click()

    expect(forehand.locator(LIMIT_VALUE)).to_have_text(str(lowest))
    expect(fixed).to_have_attribute("aria-pressed", "true")
    expect(chip(forehand, highest)).to_have_attribute("aria-pressed", "false")
    assert own_plan(forehand, table) == limit_at(lowest, PlanMode.FIXED)
    top_while_it_stood, opacity_while_it_stood = forehand.locator(PLAN_LINE).evaluate(PLACE_AND_OPACITY)

    above = first_bid_above(lowest)
    step(table.middlehand, table, AuctionAction.BID, above)

    assert_scene(table, Scene(JUST_PASSED, Marks(bubble=str(above)), ON_TURN, waits=("rearhand", "middlehand")))
    assert own_word(forehand, table) == (AuctionAction.PASS.value, None)
    expect(forehand.locator(LIMIT_VALUE)).to_have_text(str(lowest))
    expect(fixed).to_have_attribute("aria-pressed", "true")
    top, opacity = forehand.locator(PASSED_LINE).evaluate(PLACE_AND_OPACITY)
    assert top == top_while_it_stood
    assert opacity < opacity_while_it_stood
    expect(forehand.locator(f"{BAR} button:enabled")).to_have_count(0)
    expect(forehand.locator(f"{PASS_KEY}, {CHIPS}, {MORE}")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_second_tap_on_the_lit_chip_or_a_tap_on_the_cross_takes_the_limit_back_and_says_so_for_a_moment(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    forehand = table.forehand
    limit = own_values(forehand, table)[0]
    lit, note = chip(forehand, limit), forehand.locator(PLAN_NOTE)

    for take_back in (lit, forehand.get_by_role("button", name=CLEAR_LIMIT)):
        lit.click()
        expect(lit).to_have_attribute("aria-pressed", "true")
        expect(note).to_have_count(0)

        take_back.click()

        expect(note).to_have_text(LIMIT_CLEARED)
        expect(lit).to_have_attribute("aria-pressed", "false")
        expect(forehand.locator(LIMIT_VALUE)).to_have_count(0)
        assert own_plan(forehand, table) is None
    expect(note).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_weg_said_ahead_can_be_taken_back_and_passes_for_its_owner_at_his_turn(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    rearhand = table.rearhand
    weg, note = pass_key(rearhand), rearhand.locator(PLAN_NOTE)

    weg.click()

    expect(weg).to_have_attribute("aria-pressed", "true")
    expect(note).to_have_text(PASS_AHEAD)
    assert own_plan(rearhand, table) == {"kind": PlanKind.PASS.value, "value": None, "mode": None}
    assert_page_fits(rearhand)

    weg.click()

    expect(weg).to_have_attribute("aria-pressed", "false")
    expect(note).to_have_text(TAKEN_BACK)
    assert own_plan(rearhand, table) is None

    weg.click()
    expect(note).to_have_text(PASS_AHEAD)
    step(table.middlehand, table, AuctionAction.PASS)

    assert_scene(table, Scene(ON_TURN, PASSED, JUST_PASSED, waits=None))
    assert_no_controls(rearhand)
    assert own_word(rearhand, table) == (AuctionAction.PASS.value, None)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_step_the_table_takes_for_two_plans_is_heard_and_shown_as_its_chairs_own(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    watcher = table.watcher
    tap(watcher)
    wait_for_recordings_decoded(watcher, RECORDING_COUNT)
    plan_ahead(table.forehand, table, limit_at(SECOND_BID, PlanMode.FIXED))

    plan_ahead(table.middlehand, table, limit_at(THIRD_BID, PlanMode.ASK))

    wait_for_recordings_started(watcher, WORDS_OF_THE_RUN)
    opening, first_hold, raised, second_hold, topped, passed = keys_said(watcher)
    assert [opening, raised, topped, passed] == [
        f"voice.value{LOWEST_BID}",
        f"voice.value{SECOND_BID}",
        f"voice.value{THIRD_BID}",
        "voice.pass",
    ]
    assert {first_hold, second_hold} <= CONFIRMATIONS
    assert_scene(table, Scene(JUST_PASSED, Marks(bubble=str(THIRD_BID)), ON_TURN, waits=("rearhand", "middlehand")))
    assert page_errors == []


def test_no_controls_and_no_auction_word_before_a_hand(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    anna = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    open_new_table(anna, e2e_server)

    expect(anna.locator(PLAQUE)).to_have_text(WAITING_FOR_PLAYERS)
    expect(anna.get_by_text(BIDDING)).to_have_count(0)
    assert_no_controls(anna)


@pytest.mark.parametrize(("motion", "animated"), [("no-preference", True), ("reduce", False)])
def test_the_turn_ring_of_a_far_chair_breathes_and_holds_still_for_reduced_motion_and_the_own_bar_never_breathes(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], motion: str, animated: bool
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, {**DESKTOP, "reduced_motion": motion})

    expect(table.watcher.locator(FAR_TURN_CHAIR)).to_have_count(1)
    expect(table.watcher.locator(".chair[data-moving]")).to_have_count(0)
    tile = table.watcher.locator(f"{FAR_TURN_CHAIR} .tile")
    assert ("breathe" in tile.evaluate("(tile) => getComputedStyle(tile).animationName")) is animated
    expect(table.middlehand.locator(TURN_CHAIR)).to_have_count(1)
    own_tile = table.middlehand.locator(f"{TURN_CHAIR} .tile")
    assert "breathe" not in own_tile.evaluate("(tile) => getComputedStyle(tile).animationName")


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize(
    ("device_motion", "stored", "spring"),
    [
        ("no-preference", {"motionSet": "dezent"}, "bubble-dezent"),
        ("no-preference", {"motionSet": "verspielt"}, "bubble-verspielt"),
        ("reduce", {"motionSet": "dezent"}, "none"),
        ("reduce", {"motionSet": "dezent", "replayMotion": True}, "bubble-dezent"),
    ],
    ids=["dezent", "verspielt", "reduced", "reduced-but-overridden"],
)
def test_a_bid_springs_up_in_the_picked_set_and_a_bubble_that_was_already_there_stands_still(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    device_motion: str,
    stored: dict[str, Any],
    spring: str,
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, {**form_factor, "reduced_motion": device_motion})
    watcher = table.watcher
    watcher.evaluate("record => localStorage.setItem('skat.settings', record)", json.dumps(stored))
    watcher.reload()
    expect(watcher.locator(SKAT_CARD)).to_have_count(2)

    step(table.middlehand, table, AuctionAction.BID, LOWEST_BID)

    expect(watcher.locator(BUBBLE)).to_have_css("animation-name", spring)
    watcher.reload()
    expect(watcher.locator(BUBBLE)).to_have_count(1)
    expect(watcher.locator(BUBBLE)).to_have_css("animation-name", "none")
    assert page_errors == []


def seats_by_position(table: BiddingTable) -> dict[str, int]:
    answer = answer_of(table.watcher, table)
    return {chair["hand"]["position"]: chair["seat"] for chair in answer["chairs"]}


def viewers(table: BiddingTable) -> dict[str, Page]:
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


def assert_scene(table: BiddingTable, scene: Scene) -> None:
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
HOLDER = Marks(bubble=HOLD, quiet=True)
PASSED = Marks(passed=True)
# The chair whose „Weg“ is the table's latest word says it in a bubble.
JUST_PASSED = Marks(bubble=PASS, quiet=True, passed=True)
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
            Scene(HOLDER, JUST_PASSED, ON_TURN, waits=("rearhand", "forehand")),
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

    assert_scene(table, Scene(ON_TURN, PASSED, JUST_PASSED, waits=None))


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
        expect(person.locator(PLAQUE)).to_have_text(text(SOURCE_LANGUAGE, "table.waitingFor", names=name))
        assert_page_fits(person)

    watch(returning, table.server, f"{TABLE_PAGE_PREFIX}{table.id}")

    for person in (*others, returning):
        expect(person.locator(COUNTER_WORD)).to_have_text(BIDDING)


def passed_in_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> BiddingTable:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    step(table.middlehand, table, AuctionAction.PASS)
    step(table.rearhand, table, AuctionAction.PASS)
    step(table.forehand, table, AuctionAction.PASS)
    return table


def next_dealer(table: BiddingTable) -> tuple[int, str]:
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
        expect(person.locator(GIVES_LINE)).to_have_text(text(SOURCE_LANGUAGE, "table.gives", name=name))
        expect(person.locator(DEALER_MARK)).to_have_count(1)
        expect(person.locator(f".chair[data-seat='{seat}'] {DEALER_MARK}")).to_have_count(1)
    assert_page_fits(person)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_after_three_passes_every_viewer_sees_eingepasst_and_the_next_dealer_then_the_new_hand(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    held_deal_pause: HeldDealPause,
) -> None:
    table = passed_in_table(open_person, e2e_server, page_errors, form_factor)
    dealer = next_dealer(table)

    for person in table.everyone:
        assert_the_hand_is_passed_in(person, dealer)
    table.watcher.reload()
    assert_the_hand_is_passed_in(table.watcher, dealer)

    held_deal_pause.release()

    for person in table.everyone:
        expect(person.locator(COUNTER_WORD)).to_have_text(BIDDING)
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
        expect(person.locator(GIVES_LINE)).to_have_text(text(SOURCE_LANGUAGE, "table.gives", name=dealer[1]))
    for person in (*present, returning):
        expect(person.locator(COUNTER_WORD)).to_have_text(BIDDING)
