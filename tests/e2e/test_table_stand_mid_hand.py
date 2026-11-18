"""A seated person stands up during a hand from the page with an armed key; the others read it once, and the person
who stood up watches with the plus on the old chair and a lock on any other open chair of the hand.
"""

from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.style import SCENE_TOLERANCE, in_the_scene
from tests.e2e.support.table_menu import menu_button
from tests.e2e.support.tables import plate_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
STAND_UP_ARMED = text(SOURCE_LANGUAGE, "table.standUpArmed")
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
SIT_QUESTION = text(SOURCE_LANGUAGE, "table.sitQuestion")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
LOCKED = text(SOURCE_LANGUAGE, "table.chairLocked")
OWN_HAND = ".own-hand"
NOTICE = "p.notice"
NEVER_UNDER_THE_NOTICE = (".plaque", ".bubble", ".chair .fan", ".chair .tile")
# Every scene of a hand that goes on after a notice about a chair draws the pill over the top edge of the trick's far
# cards; this one stands for them.
NOTICE_SCENE = "shorten-refused"
# How far the notice reaches down into the deepest card below `cardSelector` beside it, in pixels.
NOTICE_DEPTH_INTO_A_CARD = """(root, [noticeSelector, cardSelector]) => {
    const notice = root.querySelector(noticeSelector).getBoundingClientRect();
    const depths = [...root.querySelectorAll(cardSelector)]
        .map((card) => card.getBoundingClientRect())
        .filter((card) => card.left < notice.right && notice.left < card.right)
        .map((card) => Math.min(notice.bottom, card.bottom) - Math.max(notice.top, card.top));
    return Math.max(0, ...depths);
}"""
TWO_CARDS = 2
SENTENCE_INSIDE_THE_PILL = """notice => {
    const sentence = document.createRange();
    sentence.selectNodeContents(notice.querySelector('.label'));
    const text = sentence.getBoundingClientRect();
    const pill = notice.getBoundingClientRect();
    return text.left >= pill.left && text.right <= pill.right;
}"""
# The notice leaves after a few seconds, so each page reads its boxes in the browser in one pass while it shows.
NOTICE_ON_THE_PAGE = (
    "(root, [noticeSelector, cardSelector, covers]) => {"
    + """
    const notice = root.querySelector(noticeSelector);
    if (notice === null || notice.getClientRects().length === 0) return null;
    const pill = notice.getBoundingClientRect();
    const overlaps = (box) =>
        pill.left < box.right && box.left < pill.right && pill.top < box.bottom && box.top < pill.bottom;
    const coversShown = (selector) => [...root.querySelectorAll(selector)]
        .some((element) => element.getClientRects().length > 0 && overlaps(element.getBoundingClientRect()));
    return {
        covered: covers.filter(coversShown),
        sentenceInside: ("""
    + SENTENCE_INSIDE_THE_PILL
    + """)(notice),
        depth: ("""
    + NOTICE_DEPTH_INTO_A_CARD
    + """)(root, [noticeSelector, cardSelector]),
    };
}"""
)


def stand_key_of(person: Page):
    return menu_button(person, STAND_UP)


def chair_of(person: Page, seat: int):
    return person.locator(f".chair[data-seat='{seat}']")


def stands_up_through_the_key(person: Page) -> None:
    menu_button(person, STAND_UP).click()
    person.get_by_role("button", name=STAND_UP_ARMED).click()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_menu_row_keeps_its_word_and_the_first_tap_only_arms_it(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
    seat = table.seat_at["rearhand"]
    person = table.pages[seat]
    key = stand_key_of(person)

    expect(key).to_have_attribute("title", STAND_UP)
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    key.click()

    expect(person.get_by_role("button", name=STAND_UP_ARMED)).to_have_attribute("title", STAND_UP_ARMED)
    expect(person.locator(".stand .run-out")).to_have_count(1)
    assert table.view(seat)["hand"]["waiting_seat"] is None


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_second_tap_stands_up_and_the_others_read_it_once_while_the_person_watches_with_a_plus_on_the_old_chair(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
    seat = table.seat_at["rearhand"]
    name = table.names[seat]
    person = table.pages[seat]
    others = [other for other_seat, other in table.pages.items() if other_seat != seat]
    notice = text(SOURCE_LANGUAGE, "table.standUpNotice", name=name)

    stands_up_through_the_key(person)

    for other in (*others, table.watcher):
        expect(other.get_by_text(notice)).to_have_count(1)
        expect(plate_of(other, seat)).to_have_text(SEAT_FREE)
        expect(other.locator(".chair.turn")).to_have_count(0)
    expect(person.locator(".chair.mine")).to_have_count(0)
    expect(person.locator(OWN_HAND)).to_have_count(0)
    expect(person.get_by_text(notice)).to_have_count(0)
    expect(chair_of(person, seat).get_by_role("button", name=SIT_DOWN)).to_be_visible()
    expect(chair_of(person, seat).locator(".fan-spot")).to_have_count(1)
    expect(person.locator(".chair").last).to_have_attribute("data-seat", str(seat))
    expect(person.locator(".row.stand")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_notice_about_the_chair_holds_its_sentence_covers_no_plaque_bubble_fan_or_chair_and_the_trick_as_the_scene(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
    table.play_out(TWO_CARDS)
    seat = table.seat_at["rearhand"]
    depth_in_the_scene = in_the_scene(table.watcher, NOTICE_SCENE, NOTICE_DEPTH_INTO_A_CARD, [".notice", ".play .card"])

    stands_up_through_the_key(table.pages[seat])

    for other in (*(page for other_seat, page in table.pages.items() if other_seat != seat), table.watcher):
        expect(other.locator(NOTICE)).to_have_count(1)
        shown = other.locator(":root").evaluate(
            NOTICE_ON_THE_PAGE, [NOTICE, ".trick .laid", list(NEVER_UNDER_THE_NOTICE)]
        )
        assert shown is not None
        assert shown["sentenceInside"]
        assert shown["covered"] == []
        assert shown["depth"] <= depth_in_the_scene + SCENE_TOLERANCE
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_person_who_stood_up_finds_a_lock_on_another_open_chair_and_sits_in_her_own_without_the_question(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
    seat = table.seat_at["rearhand"]
    other_seat = table.seat_at["middlehand"]
    person = table.pages[seat]

    stands_up_through_the_key(table.pages[other_seat])
    stands_up_through_the_key(person)

    expect(chair_of(person, other_seat).get_by_role("img", name=LOCKED)).to_be_visible()
    ring_style = (
        chair_of(person, other_seat)
        .get_by_role("img", name=LOCKED)
        .evaluate("tile => getComputedStyle(tile, '::before').borderTopStyle")
    )
    assert ring_style == "dashed"
    expect(chair_of(person, other_seat).get_by_role("button", name=SIT_DOWN)).to_have_count(0)
    expect(chair_of(table.watcher, other_seat).get_by_role("button", name=SIT_DOWN)).to_be_visible()

    chair_of(person, seat).get_by_role("button", name=SIT_DOWN).click()

    expect(person.locator(".chair.mine")).to_have_attribute("data-seat", str(seat))
    expect(person.get_by_role("dialog", name=SIT_QUESTION)).to_have_count(0)
    expect(chair_of(person, other_seat).get_by_role("img", name=LOCKED)).to_have_count(0)
