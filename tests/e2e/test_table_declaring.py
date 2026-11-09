import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.web.declaring import TABLE_DECLARATION_SUFFIX
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

TAKE_SKAT = catalog_text("takeSkat")
PUT_BACK = catalog_text("putBack")
ANNOUNCE = catalog_text("announceGame")
COMMAND_FAILED = catalog_text("commandFailed")
BIDDING = catalog_text("bidding")
BID_VALUE = catalog_text("bidValue")
PLAYS = catalog_text("plays")
CHOOSES = catalog_text("chooses")
DISCARDS = catalog_text("discards")
GAME_NAMES = [catalog_text(key) for key in ("gameKaro", "gameHerz", "gamePik", "gameKreuz", "gameGrand", "gameNull")]
NULL_GAME = catalog_text("gameNull")
CONTROL_NAMES = [TAKE_SKAT, PUT_BACK, ANNOUNCE, *GAME_NAMES]
HAND_CARD = ".own-hand .card"
PICKABLE_CARD = ".own-hand .card button"
SKAT_BACK = ".skat-spot .skat-card"
CARDS_IN_A_HAND = 10
CARDS_AFTER_THE_TAKE = 12
PLAQUE = ".plaque"
DECLARER_MARK = ".mark.declarer"
LONGER_THAN_THE_WON_MOMENT = 10_000
PRESSED = "aria-pressed"
# A picked card rises out of its place in the fan, which still moves while the two new cards are dealt.
RISEN_OUT_OF_ITS_PLACE = (
    "(card) => card.getBoundingClientRect().top < card.closest('.card').getBoundingClientRect().top"
)
# The fan shows each card's left strip, and the next card covers its middle, where a plain click lands.
INSIDE_THE_VISIBLE_STRIP = {"x": 8, "y": 40}


def button_of(person: Page, name: str) -> Locator:
    return person.get_by_role("button", name=name, exact=True)


def drawn_cards_of(person: Page) -> set[tuple[str, str]]:
    drawn = person.locator(".card-face").evaluate_all(
        "(faces) => faces.map((face) => [face.dataset.suit, face.dataset.rank])"
    )
    return {(suit, rank) for suit, rank in drawn}


def reload_and_wait(person: Page) -> None:
    person.reload()
    expect(person.locator(".chair")).to_have_count(3)


def tap(card: Locator) -> None:
    card.click(position=INSIDE_THE_VISIBLE_STRIP)


def expect_lifted(card: Locator) -> None:
    card.page.wait_for_function(RISEN_OUT_OF_ITS_PLACE, arg=card.element_handle())


def expect_no_controls(person: Page) -> None:
    for name in CONTROL_NAMES:
        expect(button_of(person, name)).to_have_count(0)


def pick_two_of_the_twelve(declarer: Page) -> None:
    """Picks the first two cards on the way through every rule of picking, with a reload after the first."""
    cards = declarer.locator(PICKABLE_CARD)
    tap(cards.nth(0))
    expect(button_of(declarer, PUT_BACK)).to_be_disabled()
    expect_lifted(cards.nth(0))

    reload_and_wait(declarer)
    expect(declarer.locator(PICKABLE_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    expect(declarer.locator(f"{PICKABLE_CARD}[{PRESSED}='true']")).to_have_count(0)
    expect(button_of(declarer, PUT_BACK)).to_be_disabled()

    tap(cards.nth(0))
    tap(cards.nth(1))
    expect(cards.nth(1)).to_have_attribute(PRESSED, "true")
    expect(button_of(declarer, PUT_BACK)).to_be_enabled()
    expect_lifted(cards.nth(0))
    expect_lifted(cards.nth(1))

    tap(cards.nth(2))
    expect(cards.nth(2)).to_have_attribute(PRESSED, "false")
    expect(declarer.locator(f"{PICKABLE_CARD}[{PRESSED}='true']")).to_have_count(2)

    tap(cards.nth(1))
    expect(cards.nth(1)).to_have_attribute(PRESSED, "false")
    expect(button_of(declarer, PUT_BACK)).to_be_disabled()

    tap(cards.nth(1))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_winner_takes_the_skat_puts_two_back_and_declares_with_a_reload_at_every_stage(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer

    expect(declarer.locator(SKAT_BACK)).to_have_count(2)
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect(button_of(declarer, "Hand")).to_have_count(0)
    reload_and_wait(declarer)
    expect(button_of(declarer, TAKE_SKAT)).to_be_enabled()
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect(declarer.get_by_text(BIDDING)).to_have_count(0)
    bid_plaque = f"{BID_VALUE} {table.bid_value()}"
    expect(declarer.get_by_text(bid_plaque)).to_have_count(1)
    for onlooker in (*table.others, table.watcher):
        expect(onlooker.get_by_text(bid_plaque)).to_have_count(1)

    button_of(declarer, TAKE_SKAT).click()
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    assert table.skat() <= drawn_cards_of(declarer)
    expect(button_of(declarer, PUT_BACK)).to_be_disabled()

    pick_two_of_the_twelve(declarer)
    button_of(declarer, PUT_BACK).click()
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect(declarer.get_by_text(bid_plaque)).to_have_count(1)
    expect(button_of(declarer, ANNOUNCE)).to_be_disabled()
    expect(button_of(declarer, "Null ouvert")).to_have_count(0)
    for name in GAME_NAMES:
        expect(button_of(declarer, name)).to_be_visible()

    reload_and_wait(declarer)
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect(button_of(declarer, ANNOUNCE)).to_be_disabled()

    button_of(declarer, NULL_GAME).click()
    expect(button_of(declarer, NULL_GAME)).to_have_attribute(PRESSED, "true")
    expect(button_of(declarer, ANNOUNCE)).to_be_enabled()

    button_of(declarer, ANNOUNCE).click()
    expect_no_controls(declarer)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "null", "hand": False, "ouvert": False, "announcement": "none"}
    reload_and_wait(declarer)
    expect_no_controls(declarer)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_double_tap_on_each_step_sends_exactly_one_command(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    posts: list[str] = []
    declarer.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    expected_step = f"{table.api_path}{TABLE_DECLARATION_SUFFIX}"

    button_of(declarer, TAKE_SKAT).dblclick()
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    assert len([url for url in posts if url.endswith(expected_step)]) == 1

    cards = declarer.locator(PICKABLE_CARD)
    tap(cards.nth(0))
    tap(cards.nth(1))
    posts.clear()
    button_of(declarer, PUT_BACK).dblclick()
    expect(button_of(declarer, ANNOUNCE)).to_be_visible()
    assert len([url for url in posts if url.endswith(expected_step)]) == 1

    button_of(declarer, NULL_GAME).click()
    posts.clear()
    button_of(declarer, ANNOUNCE).dblclick()
    expect_no_controls(declarer)
    assert len([url for url in posts if url.endswith(expected_step)]) == 1
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_opponents_and_watchers_see_no_controls_and_no_skat_face_at_any_stage(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    skat = table.skat()
    onlookers = [*table.others, table.watcher]

    def expect_only_onlookers_pages() -> None:
        for person in onlookers:
            expect_no_controls(person)
            assert not drawn_cards_of(person) & skat

    expect_only_onlookers_pages()

    table.declare_through_the_api(action="take")
    expect(table.declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    expect_only_onlookers_pages()

    table.declare_through_the_api(
        action="put_back",
        cards=[{"suit": suit, "rank": rank} for suit, rank in sorted(skat)],
    )
    expect(table.declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect_only_onlookers_pages()

    table.declare_through_the_api(action="declare", game="null", hand=False, ouvert=False, announcement="none")
    expect_no_controls(table.declarer)
    expect_only_onlookers_pages()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_stale_page_shows_the_refusal_and_the_stream_corrects_it(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The browser logs the refused step as a console error; that refusal is the point of this test.
    table = deal_a_declaring_table(form_factor, console=False)
    declarer = table.declarer

    def take_through_the_api_first(route: Route) -> None:
        table.declare_through_the_api(action="take")
        route.continue_()

    declarer.route(f"**{table.api_path}{TABLE_DECLARATION_SUFFIX}", take_through_the_api_first)
    button_of(declarer, TAKE_SKAT).click()

    expect(declarer.locator(".note")).to_have_text(COMMAND_FAILED)
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_keyboard_reaches_and_works_every_card_and_game(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, TAKE_SKAT).focus()
    declarer.keyboard.press("Enter")
    expect(declarer.locator(PICKABLE_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)

    cards = declarer.locator(PICKABLE_CARD)
    cards.first.focus()
    declarer.keyboard.press("Enter")
    expect(cards.first).to_have_attribute(PRESSED, "true")
    declarer.keyboard.press("Tab")
    expect(cards.nth(1)).to_be_focused()
    declarer.keyboard.press("Enter")
    expect(cards.nth(1)).to_have_attribute(PRESSED, "true")

    button_of(declarer, PUT_BACK).focus()
    declarer.keyboard.press("Enter")
    expect(button_of(declarer, ANNOUNCE)).to_be_visible()

    for name in GAME_NAMES:
        tile = button_of(declarer, name)
        tile.focus()
        declarer.keyboard.press("Enter")
        expect(tile).to_have_attribute(PRESSED, "true")
    button_of(declarer, ANNOUNCE).focus()
    declarer.keyboard.press("Enter")
    expect_no_controls(declarer)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_others_see_the_declarer_decide_at_every_stage(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = DeclaringTable(open_person, e2e_server, member_of, page_errors, form_factor, hold_the_others_clock=True)
    name = table.name_of_the_declarer()
    value = table.bid_value()
    onlookers = [*table.others, table.watcher]
    declarer_chair = f".chair[data-seat='{table.declarer_seat}']"
    declarer_fan = f"{declarer_chair} .fan .deal"

    def expect_the_plaque(*lines: str) -> None:
        for onlooker in onlookers:
            for line in lines:
                expect(onlooker.locator(PLAQUE)).to_contain_text(line)
            expect(onlooker.locator(DECLARER_MARK)).to_have_count(1)
            expect(onlooker.locator(f"{declarer_chair} {DECLARER_MARK}")).to_have_count(1)
            expect(onlooker.locator(declarer_chair)).to_have_class(re.compile(r"\bturn\b"))
            expect_no_controls(onlooker)

    expect_the_plaque(f"{name} {PLAYS}, {value}")
    for onlooker in onlookers:
        expect(onlooker.locator(".chair.out")).to_have_count(2)

    for onlooker in onlookers:
        onlooker.clock.run_for(LONGER_THAN_THE_WON_MOMENT)
        expect(onlooker.locator(".chair.out")).to_have_count(0)
        expect(onlooker.locator(SKAT_BACK)).to_have_count(2)
    expect_the_plaque(f"{BID_VALUE} {value}", f"{name} {CHOOSES}")

    table.declare_through_the_api(action="take")
    expect(table.declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    expect_the_plaque(f"{BID_VALUE} {value}", f"{name} {DISCARDS}")
    for onlooker in onlookers:
        expect(onlooker.locator(SKAT_BACK)).to_have_count(0)
        expect(onlooker.locator(declarer_fan)).to_have_count(CARDS_AFTER_THE_TAKE)
        reload_and_wait(onlooker)
    expect_the_plaque(f"{BID_VALUE} {value}", f"{name} {DISCARDS}")

    skat = sorted(table.skat())
    table.declare_through_the_api(action="put_back", cards=[{"suit": suit, "rank": rank} for suit, rank in skat])
    expect(table.declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect_the_plaque(f"{name} {DISCARDS}")

    table.declare_through_the_api(action="declare", game="null", hand=False, ouvert=False, announcement="none")
    for onlooker in onlookers:
        expect(onlooker.locator(DECLARER_MARK)).to_have_count(1)
        expect(onlooker.locator(f"{declarer_chair} {DECLARER_MARK}")).to_have_count(1)
        expect(onlooker.get_by_text(f"{name} {DISCARDS}")).to_have_count(0)
        assert onlooker.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_declarer_carries_the_mark_and_the_turn_and_keeps_the_own_plaque(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer

    expect(declarer.locator(DECLARER_MARK)).to_have_count(1)
    expect(declarer.locator(".chair.mine")).to_have_class(re.compile(r"\bturn\b"))
    expect(declarer.locator(PLAQUE)).not_to_contain_text(CHOOSES)
    expect(declarer.locator(PLAQUE)).to_contain_text(f"{BID_VALUE} {table.bid_value()}")
    assert page_errors == []
