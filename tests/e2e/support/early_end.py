"""What the tests of a shortening and of an open play read on the table page."""

from typing import TYPE_CHECKING, Literal

from playwright.sync_api import Locator, Page, Route, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.result_card import CARD

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable

COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
CARDS_AFTER_TWO_TRICKS = 6
REQUEST = ".plaque.ask"
CROSS = ".mark.declined"
OPEN_CARDS = ".open"
OPEN_TAG = ".open-tag"
PLAY_OPEN_KEY = ".copy.play-open"
SHORTEN_KEY = ".copy.shorten"
NOTICE = ".notice.seat"
NOTICE_MILLISECONDS = 4000
THREE_SECONDS_MILLISECONDS = 3000
STRIP = ".actions"
OWN_CARDS = ".own-hand .card"
OWN_HAND = ".own-hand"
COUNT_TAG = ".count-tag"


def opponents(table: PlayingTable) -> list[int]:
    return sorted(seat for seat in table.pages if seat != table.declarer_seat)


def expect_the_page_to_show_every_card_played(person: Page, played: int) -> None:
    """The page shows the table after `played` cards, its own hand and the other chairs' counts alike, so a tap on a
    key sends the table's latest version and is not refused as stale.
    """
    cards_left = 10 - played // 3
    expect(person.locator(OWN_CARDS)).to_have_count(cards_left)
    expect(person.locator(COUNT_TAG)).to_have_text([str(cards_left)] * 2)


def mark_on(person: Page, seat: int, selector: str) -> Locator:
    return person.locator(f".chair[data-seat='{seat}'] {selector}")


def expect_the_stamp(
    table: PlayingTable, word_key: Literal["result.shortened", "result.playedOpen"], by_seat: int
) -> None:
    for person in table.everyone:
        stamp = person.locator(f"{CARD} .stamp")
        expect(stamp).to_contain_text(text(SOURCE_LANGUAGE, word_key))
        expect(stamp.locator(".by")).to_have_text(table.names[by_seat][0])
        expect(person.locator(REQUEST)).to_have_count(0)


def expect_nothing_to_overflow(person: Page, parts: str = f"{REQUEST}, {NOTICE}") -> None:
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
    for part in person.locator(f"{OWN_HAND}, {STRIP}").all():
        box = part.bounding_box()
        assert box is not None
        assert box["y"] + box["height"] <= viewport["height"]


def expect_a_refused_tap_to_show_the_failure_note(person: Page, command_path: str, tap: Callable[[], None]) -> None:
    """The table refuses the command that `tap` sends to `command_path`, and the page shows its failure note."""

    def refuse(route: Route) -> None:
        route.fulfill(status=409, content_type="application/json", body="{}")

    person.route(f"**{command_path}", refuse)
    tap()
    expect(person.locator(".note")).to_have_text(COMMAND_FAILED)
