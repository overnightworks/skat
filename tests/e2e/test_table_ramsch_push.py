from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.bidding import LOWEST_BID
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.pushing import TABLE_PUSHING_TAKE_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch_stage import PLAQUE, RamschStageTable, deal
from tests.e2e.support.result_card import CARD
from tests.e2e.support.server import AlwaysTheSameDeal, skat_on_new_database

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import Route

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

# Middlehand holds a jack among its twelve (its ten and the skat), so the dimmed jacks are always there to check.
DEAL_WITH_A_JACK_FOR_MIDDLEHAND = 2
NARROW_BELOW = 900

TAKE_SKAT = text(SOURCE_LANGUAGE, "push.takeSkat")
PUSH = text(SOURCE_LANGUAGE, "table.push")
PUT_BACK = text(SOURCE_LANGUAGE, "declare.putBack")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "declare.commandFailed")
REFUSED = 409
GRAND_HAND = text(SOURCE_LANGUAGE, "push.grandHand")
GRAND_HAND_ASKED = text(SOURCE_LANGUAGE, "push.grandHandAsk")
GRAND_HAND_GAME = text(SOURCE_LANGUAGE, "game.handName", game=text(SOURCE_LANGUAGE, "game.grand"))
ANY_PLAQUE = ".plaque"
GRAND_HAND_BID = f"{text(SOURCE_LANGUAGE, 'table.bidValue')} {LOWEST_BID}"
KEYS = (TAKE_SKAT, PUSH, PUT_BACK, GRAND_HAND, GRAND_HAND_ASKED)
STRIP_CARD = ".own-hand .card button.pick"
DIMMED_CARD = ".own-hand .card.no"
PLAYABLE_CARD = ".own-hand .card.ok"
PRESSED = "aria-pressed"
CARDS_AFTER_A_TAKE = 12
# The fan shows each card's left strip, and the next card covers its middle, where a plain click lands.
INSIDE_THE_VISIBLE_STRIP = {"x": 8, "y": 40}


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, which deals every hand with a jack among middlehand's twelve."""
    with skat_on_new_database(
        tmp_path_factory, random_source=AlwaysTheSameDeal(DEAL_WITH_A_JACK_FOR_MIDDLEHAND)
    ) as server:
        yield server


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
    assert jacks > 0
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


def box_of(person: Page, name: str) -> dict[str, float]:
    box = key(person, name).bounding_box()
    assert box is not None
    return box


def play_to_the_result(table: RamschStageTable) -> None:
    """Each seat on turn plays its first legal card, until the hand's result is there."""
    while table.view(1)["result"] is None:
        for seat in table.sessions:
            legal = (table.view(seat)["hand"] or {}).get("playing", {}).get("legal_cards", [])
            if legal:
                table.step(seat, TABLE_CARD_SUFFIX, **legal[0])
                break


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_seat_on_turn_declares_a_grand_hand_with_a_second_tap_and_the_hand_plays_as_one_to_its_result_card(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor, grand_hand="allowed")
    forehand = table.pages[table.seat_of("forehand")]
    width = form_factor["viewport"]["width"]

    expect(key(forehand, GRAND_HAND)).to_be_enabled()
    expect_the_keys_in_the_frame(forehand, (TAKE_SKAT, PUSH, GRAND_HAND))
    take, push, grand = (box_of(forehand, name) for name in (TAKE_SKAT, PUSH, GRAND_HAND))
    if width < NARROW_BELOW:
        assert take["y"] == push["y"]
        assert grand["y"] >= take["y"] + take["height"]
        assert grand["width"] >= take["width"] + push["width"]
    else:
        assert take["y"] == push["y"] == grand["y"]
    for person in (*(table.pages[table.seat_of(position)] for position in ("middlehand", "rearhand")), table.watcher):
        expect_no_key(person)

    key(forehand, GRAND_HAND).click()
    expect(key(forehand, GRAND_HAND_ASKED)).to_be_visible()
    forehand.locator(PLAQUE).click()
    expect(key(forehand, GRAND_HAND)).to_be_visible()
    expect(key(forehand, GRAND_HAND_ASKED)).to_have_count(0)
    assert table.view(table.seat_of("forehand"))["hand"]["pushing"] is not None

    key(forehand, GRAND_HAND).click()
    key(forehand, GRAND_HAND_ASKED).click()

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_have_count(0)
        expect(person.locator(ANY_PLAQUE)).to_contain_text(GRAND_HAND_GAME)
        expect(person.locator(f"{ANY_PLAQUE} .game.pushes")).to_have_text(GRAND_HAND_BID)
        expect_no_key(person)
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    play_to_the_result(table)

    assert table.view(table.seat_of("forehand"))["result"]["kind"] == "declared"
    for person in table.everyone:
        expect(person.locator(CARD)).to_contain_text(GRAND_HAND_GAME)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_that_does_not_allow_it_shows_no_grand_hand_key_to_the_seat_on_turn(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor)
    forehand = table.pages[table.seat_of("forehand")]

    expect(key(forehand, TAKE_SKAT)).to_be_enabled()
    expect(key(forehand, GRAND_HAND)).to_have_count(0)


def test_a_refused_step_shows_the_failure_and_leaves_the_keys_to_tap_again(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    # The browser logs the refused step as a console error; that refusal is the point of this test.
    table = deal(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    forehand = table.pages[table.seat_of("forehand")]

    def refuse(route: Route) -> None:
        route.fulfill(status=REFUSED, content_type="application/json", body="{}")

    forehand.route(f"**{table.api_path}{TABLE_PUSHING_TAKE_SUFFIX}", refuse)
    key(forehand, TAKE_SKAT).click()

    expect(forehand.locator(".note")).to_have_text(COMMAND_FAILED)
    expect(key(forehand, TAKE_SKAT)).to_be_enabled()
    expect(key(forehand, PUSH)).to_be_enabled()
