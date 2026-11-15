"""What the tests of a shortening and of an open play read on the table page."""

from typing import TYPE_CHECKING, Literal

from playwright.sync_api import Locator, Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.result_card import CARD

if TYPE_CHECKING:
    from tests.e2e.support.hands import PlayingTable

CARDS_AFTER_TWO_TRICKS = 6
REQUEST = ".plaque.ask"
CROSS = ".mark.declined"
OPEN_CARDS = ".open"
OPEN_TAG = ".open-tag"
NOTICE = ".notice.seat"
NOTICE_MILLISECONDS = 4000
STRIP = ".actions"
OWN_CARDS = ".own-hand .card"


def opponents(table: PlayingTable) -> list[int]:
    return sorted(seat for seat in table.pages if seat != table.declarer_seat)


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


def expect_nothing_to_overflow(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    viewport = person.viewport_size
    assert viewport is not None
    for part in person.locator(f"{REQUEST}, {NOTICE}").all():
        box = part.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]
