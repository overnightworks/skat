"""A framed table tells the call where each chair's tile lies and makes the chairs the call placed see-through."""

import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.engine.bidding import VALID_BIDS
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.bidding import BiddingTable, position_of, step
from tests.e2e.support.call_frame import (
    CALL_ORIGIN,
    CHAIR,
    FRAME,
    OTHER_HOST,
    OTHER_PORT,
    STAND_IN,
    THREE_CHAIRS,
    add_sibling,
    greeting_page_holding,
    pixel_at,
    sender_from_a_sibling,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.people import DESKTOP, FORM_FACTORS
from tests.e2e.support.table_menu import menu_button
from tests.e2e.support.tables import open_new_table, plate_of, sit_in, table_id_of, watch
from tests.support.ended_tables import end_as_an_opener_closed_it

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import APIResponse, FrameLocator, Page, Route

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
STAND_UP_ARMED = text(SOURCE_LANGUAGE, "table.standUpArmed")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
OTHER_ORIGIN = f"https://{OTHER_HOST}:{OTHER_PORT}"
FOREIGN_KEY = "f" * 64
# The tiles the call is told about: those of the occupied chairs, in seat order.
LIVE_BOXES = """chairs => chairs
    .filter((chair) => chair.querySelector(".tile:not(.empty, .free)"))
    .sort((first, second) => first.dataset.seat - second.dataset.seat)
    .map((chair) => {
        const rect = chair.querySelector(".tile").getBoundingClientRect();
        return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
    })"""
DESKTOP_WIDTH = 900
# Keeps on window.closedHoles the seat of each chair that stops being see-through, from now on.
WATCHING_THE_HOLES = """() => {
    window.closedHoles = [];
    new MutationObserver((records) => {
        for (const { target } of records) {
            if (!target.hasAttribute("data-see-through")) closedHoles.push(Number(target.dataset.seat));
        }
    }).observe(document.querySelector(".room"), {
        subtree: true, attributes: true, attributeFilter: ["data-see-through"],
    });
}"""

# How far each clipped backdrop paints beyond its box by its outer shadows, and how far its clip path reaches beyond it.
CLIP_COVERS_SHADOWS = """backdrops => backdrops.map((backdrop) => {
    const box = backdrop.getBoundingClientRect();
    const [left, top, right, bottom] = /M (-?[\\d.]+) (-?[\\d.]+) H (-?[\\d.]+) V (-?[\\d.]+)/
        .exec(backdrop.style.clipPath).slice(1).map(Number);
    const shadows = getComputedStyle(backdrop).boxShadow.split(/,(?![^(]*\\))/)
        .filter((shadow) => shadow.trim() !== "none" && !shadow.includes("inset"));
    const reaches = shadows.map((shadow) => {
        const [x, y, blur, spread] = shadow.replace(/rgba?\\([^)]*\\)/, "").match(/-?[\\d.]+/g).map(Number);
        return Math.max(blur + spread - x, blur + spread + x, blur + spread - y, blur + spread + y);
    });
    return {
        cover: Math.min(-left, -top, right - box.width, bottom - box.height),
        reach: Math.max(0, ...reaches),
    };
})"""
SAMPLES = ((0.5, 0.5), (0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7))


@dataclass(frozen=True)
class Call:
    """A visitor seated at chair 1 who sees the table framed in a call page that fills the screen."""

    visitor: Page
    table: FrameLocator
    path: str
    others: tuple[Page, ...]


@contextmanager
def the_call(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    server: RunningServer,
    form_factor: dict[str, Any],
    *,
    greets: bool = False,
    other_seats: tuple[int, ...] = (2, 3),
) -> Iterator[Call]:
    visitor = open_person(server=server, **form_factor)
    path = open_new_table(visitor, server)
    others = []
    for seat in other_seats:
        other = open_person(server=server, username=f"seat{seat}-{uuid.uuid4().hex[:8]}")
        watch(other, server, path)
        sit_in(other, seat)
        expect(plate_of(other, seat)).to_have_text(YOU)
        others.append(other)
    page = greeting_page_holding(
        table_url(server, path), server.base_url, greets_every_ready=greets, filling_the_screen=True
    )
    with served_from(CALL_ORIGIN, visitor, browser_coverage, page):
        visitor.evaluate("url => location.assign(url)", f"{CALL_ORIGIN}/")
        table = visitor.frame_locator(FRAME)
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        visitor.wait_for_function("window.messages.length >= 1")
        yield Call(visitor, table, path, tuple(others))


@pytest.fixture(scope="module")
def framing_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("call-seats"), call_origin=CALL_ORIGIN)


def seat_messages(call: Call) -> list[dict[str, Any]]:
    return call.visitor.evaluate("messages.filter((message) => message.type === 'seats')")


def wait_for_seat_messages(call: Call, count: int) -> None:
    call.visitor.wait_for_function(f"messages.filter((message) => message.type === 'seats').length >= {count}")


def greet(call: Call) -> None:
    call.visitor.evaluate("greet()")


def place_all(call: Call) -> list[str]:
    """The call places every key of the latest seats and draws its stand-ins."""
    keys = [seat["key"] for seat in call.visitor.evaluate("lastSeats()")["seats"]]
    call.visitor.evaluate("keys => place(keys)", keys)
    return keys


def live_boxes(call: Call) -> list[dict[str, float]]:
    return call.table.locator(CHAIR).evaluate_all(LIVE_BOXES)


def posted_boxes(call: Call) -> list[dict[str, float]]:
    return [seat["box"] for seat in call.visitor.evaluate("lastSeats()")["seats"]]


def until(call: Call, check: Callable[[], bool]) -> None:
    """Looks again after each frame the page draws until `check` holds."""
    for _ in range(200):
        if check():
            return
        call.visitor.evaluate("() => new Promise((resolve) => requestAnimationFrame(() => resolve()))")
    pytest.fail("the page did not come to the state the test waits for")


def centre_samples(box: dict[str, float]) -> list[tuple[float, float]]:
    return [(box["x"] + box["w"] * across, box["y"] + box["h"] * down) for across, down in SAMPLES]


def shows_the_stand_in(call: Call, box: dict[str, float]) -> bool:
    # The chair's marks and shadows lie on the video, so one sample may be shaded.
    shown = [pixel_at(call.visitor, x, y) == STAND_IN for x, y in centre_samples(box)]
    return sum(shown) >= len(shown) - 1


def shows_the_table(call: Call, box: dict[str, float]) -> bool:
    return all(pixel_at(call.visitor, x, y) not in (STAND_IN, (0, 200, 0)) for x, y in centre_samples(box))


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_every_box_equals_its_tiles_rect_after_a_resize_and_only_the_desktop_own_seat_is_round(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    with the_call(open_person, browser_coverage, framing_server, form_factor, greets=True) as call:
        wait_for_seat_messages(call, 1)
        viewport = form_factor["viewport"]

        call.visitor.set_viewport_size({"width": viewport["width"], "height": viewport["height"] - 90})

        until(call, lambda: posted_boxes(call) == live_boxes(call))
        seats = call.visitor.evaluate("lastSeats()")["seats"]
        assert posted_boxes(call) == live_boxes(call)
        assert [seat["shape"] for seat in seats] == [
            "round" if form_factor["viewport"]["width"] >= DESKTOP_WIDTH else "rect",
            "rect",
            "rect",
        ]
        for seat in seats:
            if seat["shape"] == "rect":
                assert set(seat["radius"]) == {"tl", "tr", "br", "bl"}
                assert all(corner >= 0 for corner in seat["radius"].values())
            else:
                assert "radius" not in seat


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_tile_that_moves_without_a_resize_is_posted_at_its_new_box(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    with the_call(open_person, browser_coverage, framing_server, form_factor, greets=True) as call:
        wait_for_seat_messages(call, 1)
        before = posted_boxes(call)

        call.table.locator(".chair[data-seat='2']").evaluate("chair => { chair.style.translate = '17px 23px'; }")

        until(call, lambda: posted_boxes(call) == live_boxes(call) != before)
        assert posted_boxes(call)[1]["x"] == before[1]["x"] + 17


def test_the_keys_stay_over_a_reload(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True, other_seats=()) as call:
        wait_for_seat_messages(call, 1)
        before = seat_messages(call)[0]["seats"][0]["key"]

        call.table.locator("body").evaluate("() => location.reload()")
        call.visitor.wait_for_function("messages.filter((message) => message.type === 'ready').length >= 2")
        wait_for_seat_messages(call, 2)

        assert seat_messages(call)[-1]["seats"][0]["key"] == before


def test_a_table_that_ends_while_the_call_runs_posts_no_seats_and_closes_every_hole(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        wait_for_seat_messages(call, 1)
        boxes = posted_boxes(call)
        place_all(call)
        until(call, lambda: all(shows_the_stand_in(call, box) for box in boxes))

        end_as_an_opener_closed_it(
            PostgresTableTransactions(framing_server.engine), table_id_of(call.path), datetime.now(UTC)
        )
        # The open stream drops and the page asks again, which answers the ended table.
        call.visitor.context.set_offline(True)
        call.visitor.context.set_offline(False)

        call.visitor.wait_for_function("lastSeats().seats.length === 0")
        until(call, lambda: all(shows_the_table(call, box) for box in boxes))
        assert call.table.locator(".felt-paint").evaluate("paint => paint.style.clipPath") == ""


def test_a_chair_taken_over_closes_its_hole_and_the_next_seats_carries_the_new_key_alone(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True, other_seats=(2,)) as call:
        wait_for_seat_messages(call, 1)
        old_keys = place_all(call)
        old_box = posted_boxes(call)[1]
        until(call, lambda: shows_the_stand_in(call, old_box))
        before = call.visitor.evaluate("messages.length")

        menu_button(call.others[0], STAND_UP).click()
        newcomer = open_person(server=framing_server, username=f"newcomer-{uuid.uuid4().hex[:8]}")
        watch(newcomer, framing_server, call.path)
        sit_in(newcomer, 2)

        until(call, lambda: shows_the_table(call, old_box))
        call.visitor.wait_for_function(
            """([before, old]) => messages.slice(before).some((message) => message.type === "seats"
                && message.seats.length === 2 && !message.seats.some((seat) => seat.key === old))""",
            arg=[before, old_keys[1]],
        )
        later = call.visitor.evaluate(
            "before => messages.slice(before).filter((message) => message.type === 'seats')", before
        )
        assert all(old_keys[1] not in [seat["key"] for seat in message["seats"]] for message in later)


def test_a_key_that_was_not_posted_is_ignored_on_its_own(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        wait_for_seat_messages(call, 1)
        keys = [seat["key"] for seat in call.visitor.evaluate("lastSeats()")["seats"]]
        boxes = posted_boxes(call)

        call.visitor.evaluate("keys => place(keys)", [keys[1], FOREIGN_KEY])

        until(call, lambda: shows_the_stand_in(call, boxes[1]))
        assert shows_the_table(call, boxes[0])
        assert shows_the_table(call, boxes[2])


def test_a_placed_that_drops_a_key_closes_only_that_chairs_hole(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        wait_for_seat_messages(call, 1)
        keys = place_all(call)
        boxes = posted_boxes(call)
        until(call, lambda: all(shows_the_stand_in(call, box) for box in boxes))

        call.visitor.evaluate("keys => place(keys)", [keys[0], keys[2]])

        until(call, lambda: shows_the_table(call, boxes[1]))
        expect(call.table.locator(".chair[data-see-through]")).to_have_count(2)


def bid_behind_the_page(call: Call, server: RunningServer) -> None:
    """The middlehand's first bid, taken as the player's other device would."""
    table_id = table_id_of(call.path)
    by_position = {position_of(person, server, table_id): person for person in (call.visitor, *call.others)}
    table = BiddingTable(
        server,
        table_id,
        by_position["forehand"],
        by_position["middlehand"],
        by_position["rearhand"],
        call.visitor,
    )
    step(table.middlehand, table, AuctionAction.BID, VALID_BIDS[0])


def test_a_bid_step_keeps_every_hole_open_and_a_stand_closes_its_chairs_hole_at_once(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        expect(call.table.locator(".skat-card")).to_have_count(2)
        wait_for_seat_messages(call, 1)
        until(call, lambda: posted_boxes(call) == live_boxes(call))
        boxes = posted_boxes(call)
        place_all(call)
        until(call, lambda: all(shows_the_stand_in(call, box) for box in boxes))
        call.table.locator("body").evaluate(WATCHING_THE_HOLES)

        bid_behind_the_page(call, framing_server)

        expect(call.table.locator(".bubble .said")).to_have_count(1)
        call.visitor.evaluate(TWO_FRAMES)

        # The own seat settles into its new box and posts it; the call draws its stand-ins again where it is told.
        def placed_at_the_live_boxes() -> bool:
            place_all(call)
            return posted_boxes(call) == live_boxes(call)

        until(call, placed_at_the_live_boxes)
        boxes = posted_boxes(call)
        until(call, lambda: all(shows_the_stand_in(call, box) for box in boxes))
        assert call.table.locator("body").evaluate("() => closedHoles") == []

        # The stand's read is held back, so the chair's hole shuts by what the table shows alone.
        held: list[Route] = []
        call.visitor.unroute("**/person-keys")
        call.visitor.route("**/person-keys", lambda route: held.append(route))
        menu_button(call.others[0], STAND_UP).click()
        call.others[0].get_by_role("button", name=STAND_UP_ARMED).click()

        until(call, lambda: shows_the_table(call, boxes[1]))
        expect(call.table.locator(".chair[data-see-through]")).to_have_count(2)
        assert call.table.locator("body").evaluate("() => closedHoles") == [2]
        call.visitor.unroute("**/person-keys")
        for route in held:
            route.continue_()


BAD_SENDERS = ["a sibling on another origin", "a sibling on the call origin"]
HEARD_MARKERS = """() => {
    window.markers = [];
    addEventListener("message", (event) => { if (event.data?.marker !== undefined) markers.push(event.data.marker); });
}"""
TWO_FRAMES = "() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
SHOWN_AS = """(_body, state) => {
    Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
}"""


@pytest.mark.parametrize("sender", BAD_SENDERS)
def test_a_hello_and_a_placed_from_another_window_or_origin_change_nothing(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer, sender: str
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP) as call, ExitStack() as stack:
        stack.enter_context(
            served_from(OTHER_ORIGIN, call.visitor, browser_coverage, "<!doctype html><title>o</title>")
        )
        if sender == BAD_SENDERS[0]:
            sibling = add_sibling(call.visitor, "other", f'src="{OTHER_ORIGIN}/"')
        else:
            sibling = add_sibling(call.visitor, "same", 'srcdoc=""')
        send = sender_from_a_sibling(sibling)
        skat = call.visitor.locator(FRAME).element_handle().content_frame()
        assert skat is not None
        skat.evaluate(HEARD_MARKERS)

        send({"v": 1, "type": "hello", "attachment": 1, "attempt": None}, 1)
        skat.wait_for_function("marker => markers.includes(marker)", arg=1)
        assert seat_messages(call) == []

        greet(call)
        wait_for_seat_messages(call, 1)
        keys = [seat["key"] for seat in call.visitor.evaluate("lastSeats()")["seats"]]
        send({"v": 1, "type": "placed", "table": table_id_of(call.path), "keys": keys}, 2)
        skat.wait_for_function("marker => markers.includes(marker)", arg=2)
        call.visitor.evaluate(TWO_FRAMES)

        assert all(shows_the_table(call, box) for box in posted_boxes(call))


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_placed_key_lets_the_stand_in_show_through_while_the_rest_of_the_table_stays_opaque(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    with the_call(open_person, browser_coverage, framing_server, form_factor, greets=True) as call:
        wait_for_seat_messages(call, 1)
        boxes = posted_boxes(call)
        assert all(shows_the_table(call, box) for box in boxes)

        place_all(call)

        until(call, lambda: all(shows_the_stand_in(call, box) for box in boxes))
        felt = call.table.locator(".felt-paint").bounding_box()
        assert felt is not None
        assert pixel_at(call.visitor, felt["x"] + felt["width"] / 2, felt["y"] + felt["height"] / 2) != STAND_IN
        assert pixel_at(call.visitor, 2, 2) not in (STAND_IN, (0, 200, 0))
        assert call.table.locator(".felt").evaluate("felt => getComputedStyle(felt).clipPath") == "none"
        assert call.table.locator(".felt-paint").evaluate("paint => paint.style.clipPath").startswith("path(")


@pytest.mark.parametrize("table_style", ["klassik", "strandbar"])
def test_a_backdrops_clip_reaches_beyond_its_rim_and_drop_shadow_in_every_table_style(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    table_style: str,
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        wait_for_seat_messages(call, 1)
        place_all(call)
        until(call, lambda: call.table.locator(".felt-paint").evaluate("paint => paint.style.clipPath") != "")
        call.table.locator(".room").evaluate("(room, style) => { room.dataset.style = style; }", table_style)
        call.table.locator("body").evaluate(TWO_FRAMES)
        clips = call.table.locator("[data-call-backdrop]").evaluate_all(CLIP_COVERS_SHADOWS)

        assert max(clip["reach"] for clip in clips) > 0
        assert all(clip["cover"] >= clip["reach"] for clip in clips)


def test_a_new_hello_closes_every_hole_and_the_table_posts_its_seats_in_full_again(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        wait_for_seat_messages(call, 1)
        # A chair that still settles posts its new box on its own, so the post to repeat is the settled table's last.
        until(call, lambda: posted_boxes(call) == live_boxes(call))
        posted_before = len(seat_messages(call))
        boxes = posted_boxes(call)
        place_all(call)
        until(call, lambda: all(shows_the_stand_in(call, box) for box in boxes))

        call.visitor.evaluate("placedKeys = []")
        greet(call)

        wait_for_seat_messages(call, posted_before + 1)
        until(call, lambda: all(shows_the_table(call, box) for box in boxes))
        assert seat_messages(call)[posted_before - 1] == seat_messages(call)[posted_before]
        assert call.table.locator(".felt-paint").evaluate("paint => paint.style.clipPath") == ""


def test_a_failed_key_read_posts_no_seats_and_the_next_read_after_the_backoff_posts_them(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP) as call:
        call.visitor.route("**/person-keys", lambda route: route.fulfill(status=500, body="{}"))
        greet(call)
        wait_for_seat_messages(call, 1)
        assert seat_messages(call)[0]["seats"] == []

        call.visitor.unroute("**/person-keys")

        wait_for_seat_messages(call, 2)
        assert len(seat_messages(call)[-1]["seats"]) == THREE_CHAIRS


def test_a_page_that_is_hidden_posts_nothing_and_a_page_that_shows_again_posts_in_full(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=True) as call:
        wait_for_seat_messages(call, 1)
        call.table.locator("body").evaluate(SHOWN_AS, "hidden")
        # What the table posted before it was hidden may still be on its way; the call page's frames let it arrive.
        call.visitor.evaluate(TWO_FRAMES)
        posted_before = len(seat_messages(call))

        call.table.locator(".chair[data-seat='2']").evaluate("chair => { chair.style.translate = '9px 0'; }")
        call.table.locator("body").evaluate(TWO_FRAMES)
        call.visitor.evaluate(TWO_FRAMES)
        assert len(seat_messages(call)) == posted_before

        call.table.locator("body").evaluate(SHOWN_AS, "visible")

        wait_for_seat_messages(call, posted_before + 1)
        until(call, lambda: posted_boxes(call) == live_boxes(call))


def test_a_view_that_arrives_while_the_keys_are_read_is_answered_with_a_read_of_the_newest(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, other_seats=(2,)) as call:
        held: list[tuple[Route, APIResponse]] = []
        # The answer is read now and handed to the page later, so it is the keys of the view before the stand-up.
        call.visitor.route("**/person-keys", lambda route: held.append((route, route.fetch())))
        greet(call)
        until(call, lambda: len(held) == 1)

        menu_button(call.others[0], STAND_UP).click()
        until(call, lambda: len(live_boxes(call)) == 1)
        call.visitor.unroute("**/person-keys")
        route, stale_answer = held[0]
        route.fulfill(response=stale_answer)

        wait_for_seat_messages(call, 1)
        assert all(len(message["seats"]) == 1 for message in seat_messages(call))


@pytest.mark.parametrize("greets", [True, False])
def test_a_page_that_leaves_the_table_answers_no_further_hello_with_seats(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    greets: bool,
) -> None:
    with the_call(open_person, browser_coverage, framing_server, DESKTOP, greets=greets, other_seats=()) as call:
        end_as_an_opener_closed_it(
            PostgresTableTransactions(framing_server.engine), table_id_of(call.path), datetime.now(UTC), None
        )
        # The open stream drops and the page asks again, which answers the table a silent minute ended: the page leaves.
        call.visitor.context.set_offline(True)
        call.visitor.context.set_offline(False)
        call.table.locator(CHAIR).first.wait_for(state="detached")
        call.visitor.evaluate(TWO_FRAMES)
        posted_before = len(seat_messages(call))

        greet(call)
        call.visitor.evaluate(TWO_FRAMES)

        assert len(seat_messages(call)) == posted_before
