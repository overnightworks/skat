from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.table.auction import AuctionAction
from skat.table.records import PlanMode
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.bidding import (
    LIMIT_KEY,
    LIMIT_VALUE,
    MORE,
    SCALE,
    SKAT_CARD,
    STEP_KEY,
    UP_TO,
    assert_page_fits,
    chip,
    dealt_table,
    first_bid_above,
    limit_at,
    on_the_scale,
    own_plan,
    own_values,
    own_word,
    step,
)
from tests.e2e.support.people import DESKTOP, WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

HOLD = text(SOURCE_LANGUAGE, "bid.hold")
PRESS_AND_HOLD = text(SOURCE_LANGUAGE, "bid.pressAndHold")
LOWEST_BID, SECOND_BID, THIRD_BID, *_, TOP_BID = VALID_BIDS
VIEW = ".scale .view"
STANDING = ".v.at b"
ABOVE_HIS_CARDS = ".v.over"
# A value the keyboard reaches lies inside the part of the scale its fades leave clear, which the scale itself names.
CLEAR_OF_THE_FADES = """(value) => {
    const view = value.closest('.view');
    const clear = getComputedStyle(view);
    const [box, frame] = [value.getBoundingClientRect(), view.getBoundingClientRect()];
    return box.left >= frame.left + parseFloat(clear.scrollPaddingLeft) - 1
        && box.right <= frame.right - parseFloat(clear.scrollPaddingRight) + 1;
}"""
AT_ITS_END = "(view) => view.scrollLeft + view.clientWidth >= view.scrollWidth - 1"
TOP_OF_THE_HAND = "() => document.querySelector('.own-hand').getBoundingClientRect().top"


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_scale_marks_what_is_bid_and_what_his_cards_reach_and_a_value_picked_while_answering_becomes_his_limit(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    forehand = table.forehand
    reached = own_values(forehand, table)
    limit = reached[-1]
    step(table.middlehand, table, AuctionAction.BID, SECOND_BID)
    expect(forehand.locator(STEP_KEY)).to_have_text(HOLD)
    more, scale = forehand.locator(MORE), forehand.locator(SCALE)
    top_of_the_hand = forehand.evaluate(TOP_OF_THE_HAND)

    more.click()

    expect(more).to_have_attribute("aria-expanded", "true")
    expect(on_the_scale(forehand, LOWEST_BID)).to_be_disabled()
    expect(scale.locator(STANDING)).to_have_text(str(SECOND_BID))
    expect(scale.locator(STANDING)).to_be_in_viewport()
    expect(scale.locator(".suit")).to_have_count(len(reached))
    expect(scale.locator(f"{ABOVE_HIS_CARDS} b").first).to_have_text(str(first_bid_above(limit)))
    expect(scale.locator(ABOVE_HIS_CARDS).first.locator(".hint")).to_have_text(PRESS_AND_HOLD)
    expect(scale.locator(".hint")).to_have_count(1)
    expect(forehand.locator(SKAT_CARD).first).to_be_hidden()
    assert forehand.evaluate(TOP_OF_THE_HAND) == top_of_the_hand
    assert_page_fits(forehand)

    on_the_scale(forehand, limit).click()

    expect(forehand.locator(STEP_KEY)).to_have_text(HOLD)
    expect(forehand.locator(LIMIT_KEY)).to_have_text(f"{UP_TO} {limit}")
    assert_page_fits(forehand)

    forehand.locator(LIMIT_KEY).click()

    # Set on his turn, the limit answers for him at once.
    expect(forehand.locator(STEP_KEY)).to_have_count(0)
    expect(scale.locator(".v.mine b")).to_have_text(str(limit))
    expect(chip(forehand, limit)).to_have_attribute("aria-pressed", "true")
    assert own_plan(forehand, table) == limit_at(limit, PlanMode.ASK)
    assert own_word(forehand, table) == (AuctionAction.HOLD.value, SECOND_BID)

    step(table.middlehand, table, AuctionAction.BID, THIRD_BID)

    expect(scale.locator(STANDING)).to_have_text(str(THIRD_BID))
    expect(on_the_scale(forehand, SECOND_BID)).to_be_disabled()

    more.click()

    expect(scale).to_have_count(0)
    expect(forehand.locator(SKAT_CARD).first).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_picks_a_value_his_cards_reach_and_the_bidders_key_says_it_at_once(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand
    jump = own_values(middlehand, table)[-1]
    middlehand.locator(MORE).click()
    picked = on_the_scale(middlehand, jump)

    picked.click()

    expect(picked).to_have_attribute("aria-pressed", "true")
    expect(middlehand.locator(STEP_KEY)).to_have_text(str(jump))
    expect(middlehand.locator(LIMIT_KEY)).to_have_text(f"{UP_TO} {jump}")
    assert_page_fits(middlehand)

    middlehand.locator(STEP_KEY).click()

    expect(table.forehand.locator(STEP_KEY)).to_have_text(HOLD)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, jump)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_above_his_cards_picks_nothing_and_a_hold_picks_the_value_for_a_limit_no_game_of_his_reaches(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand
    above = first_bid_above(own_values(middlehand, table)[-1])
    middlehand.locator(MORE).click()
    high = on_the_scale(middlehand, above)

    high.click()

    expect(high).to_have_attribute("aria-pressed", "false")
    expect(middlehand.locator(LIMIT_KEY)).to_have_count(0)

    high.hover()
    middlehand.mouse.down()
    expect(high).to_have_attribute("aria-pressed", "true")
    middlehand.mouse.up()

    expect(middlehand.locator(STEP_KEY)).to_have_text(str(above))

    middlehand.locator(LIMIT_KEY).click()

    # Set on his turn, the limit bids for him at once: the next value, not the limit.
    expect(table.forehand.locator(STEP_KEY)).to_have_text(HOLD)
    expect(middlehand.locator(LIMIT_VALUE)).to_have_text(str(above))
    expect(middlehand.locator(".bid-line .suit")).to_have_count(0)
    assert own_plan(middlehand, table) == limit_at(above, PlanMode.ASK)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, LOWEST_BID)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_keyboard_walks_the_scale_clear_of_its_fades_and_enter_picks_a_value_above_his_cards_at_once(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand
    middlehand.locator(MORE).press("Enter")
    values = middlehand.locator(f"{SCALE} .v")
    expect(values).to_have_count(len(VALID_BIDS))

    values.first.focus()
    for index in range(len(VALID_BIDS)):
        expect(values.nth(index)).to_be_focused()
        assert values.nth(index).evaluate(CLEAR_OF_THE_FADES) is True
        if index < len(VALID_BIDS) - 1:
            middlehand.keyboard.press("Tab")
    middlehand.keyboard.press("Enter")

    expect(values.last).to_have_attribute("aria-pressed", "true")
    expect(middlehand.locator(STEP_KEY)).to_have_text(str(TOP_BID))

    middlehand.locator(STEP_KEY).press("Enter")

    expect(table.forehand.locator(STEP_KEY)).to_have_text(HOLD)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, TOP_BID)


def test_a_mouse_wheels_the_scale_to_the_top_value_and_has_a_bar_to_drag(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, DESKTOP)
    middlehand = table.middlehand
    middlehand.locator(MORE).click()
    view = middlehand.locator(VIEW)
    assert view.evaluate("(view) => getComputedStyle(view).scrollbarWidth") == "thin"
    assert view.evaluate(AT_ITS_END) is False

    view.hover()
    middlehand.mouse.wheel(10_000, 0)
    middlehand.wait_for_function(f"() => ({AT_ITS_END})(document.querySelector({VIEW!r}))")
    top = on_the_scale(middlehand, TOP_BID)
    top.hover()
    middlehand.mouse.down()
    expect(top).to_have_attribute("aria-pressed", "true")
    middlehand.mouse.up()

    middlehand.locator(STEP_KEY).click()

    expect(table.forehand.locator(STEP_KEY)).to_have_text(HOLD)
    assert own_word(middlehand, table) == (AuctionAction.BID.value, TOP_BID)
