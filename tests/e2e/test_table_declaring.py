import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import CARDS_IN_PLAY, PlayingTable
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
HAND = catalog_text("hand")
SCHNEIDER = catalog_text("levelSchneider")
SCHWARZ = catalog_text("levelSchwarz")
ANNOUNCED_WORDS = {"schneider": catalog_text("announcedSchneider"), "schwarz": catalog_text("announcedSchwarz")}
COMMAND_FAILED = catalog_text("commandFailed")
BIDDING = catalog_text("bidding")
BID_VALUE = catalog_text("bidValue")
PLAYS = catalog_text("plays")
CHOOSES = catalog_text("chooses")
DISCARDS = catalog_text("discards")
GAME_NAMES = [catalog_text(key) for key in ("gameKaro", "gameHerz", "gamePik", "gameKreuz", "gameGrand", "gameNull")]
NULL_GAME = catalog_text("gameNull")
CONTROL_NAMES = [TAKE_SKAT, HAND, PUT_BACK, ANNOUNCE, SCHNEIDER, SCHWARZ, *GAME_NAMES]
HAND_CARD = ".own-hand .card"
PICKABLE_CARD = ".own-hand .card button"
SKAT_BACK = ".skat-spot .skat-card"
CARDS_IN_A_HAND = 10
CARDS_AFTER_THE_TAKE = 12
PLAQUE = ".plaque"
HELD_LEVEL = ".declare .held"
ANNOUNCED_MARK = ".plaque .announced"
LEVEL_NAMES = {"schneider": SCHNEIDER, "schwarz": SCHWARZ}
RESULT_CARD = ".result"
NULL_OUVERT = "Null ouvert"
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
    expect(button_of(declarer, HAND)).to_be_enabled()
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
    expect(button_of(declarer, NULL_OUVERT)).to_have_count(0)
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
    expect(declarer.locator(PLAQUE)).to_contain_text(NULL_GAME)
    expect(declarer.locator(PLAQUE)).not_to_contain_text(HAND)
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

    button_of(declarer, TAKE_SKAT).dblclick()
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    assert len([url for url in posts if url.endswith(f"{table.api_path}{TABLE_DECLARING_TAKE_SUFFIX}")]) == 1

    cards = declarer.locator(PICKABLE_CARD)
    tap(cards.nth(0))
    tap(cards.nth(1))
    posts.clear()
    button_of(declarer, PUT_BACK).dblclick()
    expect(button_of(declarer, ANNOUNCE)).to_be_visible()
    assert len([url for url in posts if url.endswith(f"{table.api_path}{TABLE_DECLARING_PUT_BACK_SUFFIX}")]) == 1

    button_of(declarer, NULL_GAME).click()
    posts.clear()
    button_of(declarer, ANNOUNCE).dblclick()
    expect_no_controls(declarer)
    assert len([url for url in posts if url.endswith(f"{table.api_path}{TABLE_DECLARING_DECLARE_SUFFIX}")]) == 1
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

    declarer.route(f"**{table.api_path}{TABLE_DECLARING_TAKE_SUFFIX}", take_through_the_api_first)
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


HAND_GAMES = [("herz", "gameHerz"), ("grand", "gameGrand"), ("null", "gameNull")]


def expect_the_choice(declarer: Page) -> None:
    expect(button_of(declarer, TAKE_SKAT)).to_be_enabled()
    expect(button_of(declarer, HAND)).to_be_enabled()
    expect(declarer.locator(SKAT_BACK)).to_have_count(2)
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)


def expect_the_hand_panel(declarer: Page) -> None:
    for name in GAME_NAMES:
        expect(button_of(declarer, name)).to_be_visible()
    expect(declarer.locator(HELD_LEVEL)).to_have_text(HAND)
    for level in (SCHNEIDER, SCHWARZ):
        expect(button_of(declarer, level)).to_be_enabled()
        expect(button_of(declarer, level)).to_have_attribute(PRESSED, "false")
    expect(button_of(declarer, ANNOUNCE)).to_be_disabled()
    expect(button_of(declarer, NULL_OUVERT)).to_have_count(0)
    expect(button_of(declarer, TAKE_SKAT)).to_have_count(0)
    expect(declarer.locator(SKAT_BACK)).to_have_count(2)
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)


def overlaps(first: dict[str, float], second: dict[str, float]) -> bool:
    return (
        first["x"] < second["x"] + second["width"]
        and second["x"] < first["x"] + first["width"]
        and first["y"] < second["y"] + second["height"]
        and second["y"] < first["y"] + first["height"]
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize(("token", "word_key"), HAND_GAMES)
def test_the_declarer_declares_each_game_as_hand_after_a_page_step_and_a_reload_returns_to_the_choice(
    deal_a_declaring_table: Callable[..., DeclaringTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
    token: str,
    word_key: str,
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    posts: list[str] = []
    declarer.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    expect_the_choice(declarer)

    button_of(declarer, HAND).click()
    expect_the_hand_panel(declarer)
    assert posts == []
    assert table.declaring_as_the_declarer_sees_it()["stage"] == "choosing"
    for onlooker in (*table.others, table.watcher):
        expect_no_controls(onlooker)
        expect(onlooker.locator(PLAQUE)).to_contain_text(CHOOSES)

    reload_and_wait(declarer)
    expect_the_choice(declarer)
    assert table.declaring_as_the_declarer_sees_it()["stage"] == "choosing"

    button_of(declarer, HAND).click()
    button_of(declarer, catalog_text(word_key)).click()
    expect(button_of(declarer, ANNOUNCE)).to_be_enabled()
    for far_fan in declarer.locator(".chair:not(.mine) .fan").all():
        assert not overlaps(far_fan.bounding_box(), declarer.locator(".declare").bounding_box())
    assert declarer.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    button_of(declarer, ANNOUNCE).click()
    expect_no_controls(declarer)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": token, "hand": True, "ouvert": False, "announcement": "none"}
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_double_tap_on_hand_sends_nothing_and_on_announce_exactly_one_command(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    posts: list[str] = []
    declarer.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)

    button_of(declarer, HAND).dblclick()
    expect_the_hand_panel(declarer)
    assert posts == []

    button_of(declarer, NULL_GAME).click()
    button_of(declarer, ANNOUNCE).dblclick()
    expect_no_controls(declarer)
    assert len([url for url in posts if url.endswith(f"{table.api_path}{TABLE_DECLARING_DECLARE_SUFFIX}")]) == 1
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_keyboard_reaches_and_works_hand_every_game_and_announce(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, HAND).focus()
    declarer.keyboard.press("Enter")
    expect_the_hand_panel(declarer)

    for name in GAME_NAMES:
        tile = button_of(declarer, name)
        tile.focus()
        declarer.keyboard.press("Enter")
        expect(tile).to_have_attribute(PRESSED, "true")
    button_of(declarer, ANNOUNCE).focus()
    declarer.keyboard.press("Enter")
    expect_no_controls(declarer)
    assert table.declaring_as_the_declarer_sees_it()["declaration"]["hand"] is True
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_hand_panel_and_its_game_stay_through_a_new_view_and_give_way_to_a_take_elsewhere(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, HAND).click()
    button_of(declarer, NULL_GAME).click()
    version = table.declaring_as_the_declarer_sees_it()
    reload_and_wait(table.others[0])
    expect(table.others[0].locator(".chair.mine")).to_be_visible()
    assert table.declaring_as_the_declarer_sees_it() == version
    expect(button_of(declarer, NULL_GAME)).to_have_attribute(PRESSED, "true")
    expect(declarer.locator(HELD_LEVEL)).to_have_text(HAND)
    expect(button_of(declarer, ANNOUNCE)).to_be_enabled()

    table.declare_through_the_api(action="take")
    expect(declarer.locator(HAND_CARD)).to_have_count(CARDS_AFTER_THE_TAKE)
    expect(button_of(declarer, PUT_BACK)).to_be_visible()
    expect(declarer.locator(HELD_LEVEL)).to_have_count(0)
    expect(button_of(declarer, SCHNEIDER)).to_have_count(0)
    expect(button_of(declarer, SCHWARZ)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_grand_hand_game_is_named_on_every_plaque_and_result_card(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    declaring = deal_a_declaring_table(form_factor)
    button_of(declaring.declarer, HAND).click()
    button_of(declaring.declarer, catalog_text("gameGrand")).click()
    button_of(declaring.declarer, ANNOUNCE).click()
    expect_no_controls(declaring.declarer)
    table = PlayingTable(declaring, None)

    grand_hand = f"{catalog_text('gameGrand')} {HAND}"
    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(grand_hand)
        expect(person.locator(ANNOUNCED_MARK)).to_have_count(0)
    assert table.declaring.declaring_as_the_declarer_sees_it()["declaration"]["hand"] is True
    table.play_out(CARDS_IN_PLAY)
    for person in table.everyone:
        expect(person.locator(RESULT_CARD)).to_contain_text(grand_hand)
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert table.result()["hand"] is True
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_ladder_offers_one_level_at_a_time_and_a_reload_returns_to_the_choice(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    declarer = deal_a_declaring_table(form_factor).declarer
    button_of(declarer, HAND).click()
    expect_the_hand_panel(declarer)

    button_of(declarer, SCHNEIDER).click()
    expect(button_of(declarer, SCHNEIDER)).to_have_attribute(PRESSED, "true")
    button_of(declarer, SCHWARZ).click()
    expect(button_of(declarer, SCHNEIDER)).to_have_attribute(PRESSED, "false")
    expect(button_of(declarer, SCHWARZ)).to_have_attribute(PRESSED, "true")
    button_of(declarer, SCHWARZ).click()
    expect(button_of(declarer, SCHWARZ)).to_have_attribute(PRESSED, "false")

    button_of(declarer, SCHNEIDER).click()
    reload_and_wait(declarer)
    expect_the_choice(declarer)
    button_of(declarer, HAND).click()
    expect_the_hand_panel(declarer)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_last_tap_on_a_level_clears_it_and_the_game_declares_without_an_announcement(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, HAND).click()
    for level in (SCHNEIDER, SCHWARZ, SCHWARZ):
        button_of(declarer, level).click()
    button_of(declarer, catalog_text("gameHerz")).click()
    button_of(declarer, ANNOUNCE).click()
    expect_no_controls(declarer)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "herz", "hand": True, "ouvert": False, "announcement": "none"}
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_choosing_null_hides_the_levels_and_declares_null_hand_without_an_announcement(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, HAND).click()
    button_of(declarer, SCHWARZ).click()
    button_of(declarer, NULL_GAME).click()
    expect(button_of(declarer, SCHNEIDER)).to_have_count(0)
    expect(button_of(declarer, SCHWARZ)).to_have_count(0)
    button_of(declarer, catalog_text("gameGrand")).click()
    expect(button_of(declarer, SCHWARZ)).to_have_attribute(PRESSED, "false")
    button_of(declarer, NULL_GAME).click()
    button_of(declarer, ANNOUNCE).click()
    expect_no_controls(declarer)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "null", "hand": True, "ouvert": False, "announcement": "none"}
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize(
    ("token", "word_key", "level"), [("herz", "gameHerz", "schneider"), ("grand", "gameGrand", "schwarz")]
)
def test_an_announced_hand_game_is_stored_with_one_command_and_every_plaque_names_it_without_covering_a_fan(
    deal_a_declaring_table: Callable[..., DeclaringTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
    token: str,
    word_key: str,
    level: str,
) -> None:
    declaring = deal_a_declaring_table(form_factor)
    declarer = declaring.declarer
    posts: list[str] = []
    declarer.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    button_of(declarer, HAND).click()
    button_of(declarer, catalog_text(word_key)).click()
    button_of(declarer, LEVEL_NAMES[level]).click()
    button_of(declarer, ANNOUNCE).dblclick()
    expect_no_controls(declarer)
    assert len([url for url in posts if url.endswith(f"{declaring.api_path}{TABLE_DECLARING_DECLARE_SUFFIX}")]) == 1
    declaration = declaring.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": token, "hand": True, "ouvert": False, "announcement": level}
    table = PlayingTable(declaring, None)

    reload_and_wait(declarer)
    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(f"{catalog_text(word_key)} {HAND}")
        expect(person.locator(ANNOUNCED_MARK)).to_have_text(ANNOUNCED_WORDS[level])
        plaque = person.locator(PLAQUE).bounding_box()
        for covered in (*person.locator(".fan-spot").all(), *person.locator(".own-hand").all()):
            assert not overlaps(plaque, covered.bounding_box())
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page_errors == []
