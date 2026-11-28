"""What the tests of a shortening and of an open play read on the table page."""

from typing import TYPE_CHECKING, Literal

from playwright.sync_api import Locator, Page, Route, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
CARDS_AFTER_TWO_TRICKS = 6
REQUEST = old_surface.REQUEST
CROSS = old_surface.DECLINED_MARK
OPEN_CARDS = old_surface.OPEN_CARDS
OPEN_TAG = old_surface.OPEN_TAG
NOTICE = old_surface.SEAT_NOTICE
NOTICE_MILLISECONDS = 4000
THREE_SECONDS_MILLISECONDS = 3000


def opponents(table: PlayingTable) -> list[int]:
    return sorted(seat for seat in table.pages if seat != table.declarer_seat)


def expect_the_page_to_show_every_card_played(person: Page, played: int) -> None:
    """The page shows the table after `played` cards, its own hand and the other chairs' counts alike, so a tap on a
    key sends the table's latest version and is not refused as stale.
    """
    cards_left = 10 - played // 3
    expect(old_surface.own_cards(person)).to_have_count(cards_left)
    expect(old_surface.count_tags(person)).to_have_text([str(cards_left)] * 2)


def mark_on(person: Page, seat: int, selector: str) -> Locator:
    return old_surface.in_chair(person, seat, selector)


def expect_the_stamp(
    table: PlayingTable, word_key: Literal["result.shortened", "result.playedOpen"], by_seat: int
) -> None:
    for person in table.everyone:
        expect(old_surface.result_stamp(person)).to_contain_text(text(SOURCE_LANGUAGE, word_key))
        expect(old_surface.result_stamp_author(person)).to_have_text(table.names[by_seat][0])
        expect(old_surface.requests(person)).to_have_count(0)


def expect_nothing_to_overflow(person: Page, parts: str = old_surface.REQUEST_AND_NOTICE) -> None:
    """The page does not scroll sideways and every part the selector names lies inside the viewport."""
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    viewport = person.viewport_size
    assert viewport is not None
    # One evaluation measures every part at once: a timed notice that leaves between two measurements is no failure.
    boxes = person.locator(parts).evaluate_all(
        "parts => parts.map(part => { const { x, width } = part.getBoundingClientRect(); return { x, width }; })"
    )
    for box in boxes:
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]


def expect_the_hand_and_the_strip_on_the_first_screen(person: Page) -> None:
    """The own hand and the strip of keys lie above the lower edge of the screen."""
    viewport = person.viewport_size
    assert viewport is not None
    for part in old_surface.own_hand_and_actions(person).all():
        box = part.bounding_box()
        assert box is not None
        assert box["y"] + box["height"] <= viewport["height"]


def expect_a_refused_tap_to_show_the_failure_note(person: Page, command_path: str, tap: Callable[[], None]) -> None:
    """The table refuses the command that `tap` sends to `command_path`, and the page shows its failure note."""

    def refuse(route: Route) -> None:
        route.fulfill(status=409, content_type="application/json", body="{}")

    person.route(f"**{command_path}", refuse)
    tap()
    expect(old_surface.note(person)).to_have_text(COMMAND_FAILED)
