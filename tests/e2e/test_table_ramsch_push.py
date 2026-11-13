from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.ramsch_stage import RamschStageTable, deal

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

TAKE_SKAT = text(SOURCE_LANGUAGE, "push.takeSkat")
PUSH = text(SOURCE_LANGUAGE, "table.push")
PUT_BACK = text(SOURCE_LANGUAGE, "declare.putBack")
KEYS = (TAKE_SKAT, PUSH, PUT_BACK)
STRIP_CARD = ".own-hand .card button.pick"
DIMMED_CARD = ".own-hand .card.no"
PLAYABLE_CARD = ".own-hand .card.ok"
PRESSED = "aria-pressed"
CARDS_AFTER_A_TAKE = 12
# The fan shows each card's left strip, and the next card covers its middle, where a plain click lands.
INSIDE_THE_VISIBLE_STRIP = {"x": 8, "y": 40}


def key(person: Page, name: str) -> Locator:
    return person.get_by_role("button", name=name, exact=True)


def expect_no_key(person: Page) -> None:
    for name in KEYS:
        expect(key(person, name)).to_have_count(0)


def expect_the_keys_in_the_frame(person: Page, names: tuple[str, ...]) -> None:
    viewport = person.viewport_size
    assert viewport is not None
    for name in names:
        box = key(person, name).bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]


def jacks_in_the_hand_of(table: RamschStageTable, position: str) -> int:
    seat = table.seat_of(position)
    return sum(card["rank"] == "jack" for card in table.view(seat)["hand"]["own_cards"])


def tap(card: Locator) -> None:
    card.click(position=INSIDE_THE_VISIBLE_STRIP)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_each_seat_on_turn_takes_or_pushes_on_the_page_and_puts_two_cards_back_with_the_locked_ones_dimmed(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor)
    forehand, middlehand, rearhand = (
        table.pages[table.seat_of(position)] for position in ("forehand", "middlehand", "rearhand")
    )

    expect(key(forehand, TAKE_SKAT)).to_be_enabled()
    expect(key(forehand, PUSH)).to_be_enabled()
    expect_the_keys_in_the_frame(forehand, (TAKE_SKAT, PUSH))
    for person in (middlehand, rearhand, table.watcher):
        expect_no_key(person)

    version = table.view(table.seat_of("forehand"))["version"]
    key(forehand, PUSH).dblclick()

    expect(key(middlehand, TAKE_SKAT)).to_be_enabled()
    expect(key(middlehand, PUSH)).to_be_enabled()
    expect_no_key(forehand)
    assert table.view(table.seat_of("forehand"))["version"] == version + 1
    table.expect_the_turn_at("middlehand")

    key(middlehand, TAKE_SKAT).click()

    strip = middlehand.locator(STRIP_CARD)
    expect(strip).to_have_count(CARDS_AFTER_A_TAKE)
    jacks = jacks_in_the_hand_of(table, "middlehand")
    expect(middlehand.locator(DIMMED_CARD)).to_have_count(jacks)
    expect(middlehand.locator(f"{STRIP_CARD}:disabled")).to_have_count(jacks)
    expect(key(middlehand, PUT_BACK)).to_be_disabled()
    allowed = [card for card in strip.all() if card.is_enabled()]
    assert len(allowed) == CARDS_AFTER_A_TAKE - jacks
    tap(allowed[0])
    expect(key(middlehand, PUT_BACK)).to_be_disabled()
    tap(allowed[1])
    expect(allowed[1]).to_have_attribute(PRESSED, "true")
    expect(key(middlehand, PUT_BACK)).to_be_enabled()
    key(middlehand, PUT_BACK).click()

    expect(key(rearhand, TAKE_SKAT)).to_be_enabled()
    expect(middlehand.locator(STRIP_CARD)).to_have_count(0)
    table.expect_the_turn_at("rearhand")

    key(rearhand, PUSH).click()

    for person in table.everyone:
        expect_no_key(person)
    table.expect_the_turn_at("forehand")
    expect(forehand.locator(PLAYABLE_CARD).first).to_be_visible()
    table.expect_nothing_to_overflow()
