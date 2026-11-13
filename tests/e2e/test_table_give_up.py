from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.playing import TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import button_of, reload_and_wait
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.name_lists import waiting_for
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.result_card import CARD

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

ACCEPT = text(SOURCE_LANGUAGE, "table.accept")
PLAY_ON = text(SOURCE_LANGUAGE, "table.playOn")
SAID_NO = text(SOURCE_LANGUAGE, "table.saidNo")
NO_ANSWER_YET = text(SOURCE_LANGUAGE, "table.noAnswerYet")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
KREUZ = text(SOURCE_LANGUAGE, "game.kreuz")
REQUEST = ".plaque.ask"
CROSS = ".mark.declined"
CARDS_AFTER_TWO_TRICKS = 6


def wants_to_give_up(asker: str) -> str:
    return text(SOURCE_LANGUAGE, "table.wantsToGiveUp", name=asker)


@pytest.fixture
def deal_a_request(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    """A declared game after two tricks at which the declarer has asked to give up; every page shows the request."""

    def deal(form_factor: dict[str, Any], *, console: bool = True) -> PlayingTable:
        table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, console=console)
        table.play_out(CARDS_AFTER_TWO_TRICKS)
        table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
        for person in table.everyone:
            expect(person.locator(REQUEST)).to_be_visible()
        return table

    return deal


def opponents(table: PlayingTable) -> list[int]:
    return [seat for seat in table.pages if seat != table.declarer_seat]


def crossed(person: Page, seat: int) -> Any:
    return person.locator(f".chair[data-seat='{seat}'] {CROSS}")


def expect_the_game_again(table: PlayingTable) -> None:
    for person in table.everyone:
        expect(person.locator(".plaque")).to_have_text(KREUZ)
        expect(person.locator(CROSS)).to_have_count(0)


def expect_the_request_without_a_no(table: PlayingTable) -> None:
    asker = table.names[table.declarer_seat]
    first, second = opponents(table)
    for seat in (first, second):
        person = table.pages[seat]
        expect(person.locator(REQUEST)).to_contain_text(wants_to_give_up(asker))
        expect(button_of(person, ACCEPT)).to_be_visible()
        expect(button_of(person, PLAY_ON)).to_be_visible()
    expect(table.watcher.locator(REQUEST)).to_contain_text(wants_to_give_up(asker))
    expect(table.watcher.locator(f"{REQUEST} button")).to_have_count(0)
    waiting = waiting_for([table.names[first], table.names[second]])
    expect(table.pages[table.declarer_seat].locator(REQUEST)).to_contain_text(waiting)
    expect(table.pages[table.declarer_seat].locator(f"{REQUEST} button")).to_have_count(0)
    expect(table.pages[table.declarer_seat].locator(f".mark.unanswered[title='{NO_ANSWER_YET}']")).to_have_count(2)


def expect_nothing_to_overflow(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    viewport = person.viewport_size
    assert viewport is not None
    for part in (person.locator(REQUEST), *person.locator(f"{REQUEST} button").all()):
        box = part.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_request_shows_its_asker_to_everyone_and_the_answers_to_the_other_side(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_request(form_factor)

    expect_the_request_without_a_no(table)
    for person in table.everyone:
        expect(person.locator(CROSS)).to_have_count(0)
        expect_nothing_to_overflow(person)
    assert page_errors == []


def test_a_no_puts_a_cross_on_its_chair_for_everyone_and_leaves_that_opponent_only_the_yes(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_request(PHONE)
    said_no, other = opponents(table)

    button_of(table.pages[said_no], PLAY_ON).click()

    for person in table.everyone:
        expect(crossed(person, said_no)).to_have_attribute("title", SAID_NO)
        expect(person.locator(CROSS)).to_have_count(1)
    expect(button_of(table.pages[said_no], ACCEPT)).to_be_visible()
    expect(button_of(table.pages[said_no], PLAY_ON)).to_have_count(0)
    expect(button_of(table.pages[other], PLAY_ON)).to_be_visible()
    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(REQUEST)).to_contain_text(waiting_for([table.names[other]]))
    expect(declarer.locator(f".mark.unanswered[title='{NO_ANSWER_YET}']")).to_have_count(1)
    assert page_errors == []


@pytest.mark.parametrize("who_says_yes", [0, 1], ids=["the one who said no", "the other opponent"])
def test_a_yes_after_a_no_ends_the_game_on_every_page(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str], who_says_yes: int
) -> None:
    table = deal_a_request(PHONE)
    said_no = opponents(table)[0]
    button_of(table.pages[said_no], PLAY_ON).click()
    expect(crossed(table.pages[said_no], said_no)).to_be_visible()

    button_of(table.pages[opponents(table)[who_says_yes]], ACCEPT).click()

    for person in table.everyone:
        expect(person.locator(CARD)).to_be_visible()
        expect(person.locator(REQUEST)).to_have_count(0)
    assert page_errors == []


def test_two_nos_bring_the_game_line_back_and_the_crosses_go(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_request(PHONE)

    first, second = opponents(table)
    button_of(table.pages[first], PLAY_ON).click()
    expect(crossed(table.pages[second], first)).to_be_visible()
    button_of(table.pages[second], PLAY_ON).click()

    expect_the_game_again(table)
    assert page_errors == []


def test_a_card_takes_the_request_back_on_every_page(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_request(PHONE)
    button_of(table.pages[opponents(table)[0]], PLAY_ON).click()
    expect(table.watcher.locator(CROSS)).to_have_count(1)

    table.play_out(1)

    expect_the_game_again(table)
    assert page_errors == []


def test_a_reload_in_every_role_shows_the_request_as_it_stands(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_request(PHONE)
    said_no, other = opponents(table)
    button_of(table.pages[said_no], PLAY_ON).click()
    expect(crossed(table.watcher, said_no)).to_be_visible()

    for person in table.everyone:
        reload_and_wait(person)

    asker = table.names[table.declarer_seat]
    for person in table.everyone:
        expect(crossed(person, said_no)).to_be_visible()
        expect(person.locator(CROSS)).to_have_count(1)
    expect(button_of(table.pages[said_no], ACCEPT)).to_be_visible()
    expect(button_of(table.pages[said_no], PLAY_ON)).to_have_count(0)
    expect(button_of(table.pages[other], PLAY_ON)).to_be_visible()
    expect(table.watcher.locator(REQUEST)).to_contain_text(wants_to_give_up(asker))
    expect(table.watcher.locator(f"{REQUEST} button")).to_have_count(0)
    expect(table.pages[table.declarer_seat].locator(REQUEST)).to_contain_text(waiting_for([table.names[other]]))
    assert page_errors == []


def test_an_answer_to_a_request_a_card_took_back_shows_the_failure_and_ends_nothing(
    deal_a_request: Callable[..., PlayingTable],
) -> None:
    # The browser logs the refused answer as a console error; that refusal is the point of this test.
    table = deal_a_request(PHONE, console=False)
    answering = table.pages[opponents(table)[0]]

    def play_a_card_first(route: Route) -> None:
        table.play_out(1)
        route.continue_()

    answering.route(f"**{table.declaring.api_path}{TABLE_GIVE_UP_AGREE_SUFFIX}", play_a_card_first)
    button_of(answering, ACCEPT).click()

    expect(answering.locator(".note")).to_have_text(COMMAND_FAILED)
    expect_the_game_again(table)
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)


HELD_CARDS = ".controls.held"
OWN_CARDS = ".own-hand .card"


def gives_up(opponent: str) -> str:
    return text(SOURCE_LANGUAGE, "table.givesUp", name=opponent)


@pytest.fixture
def deal_an_opponents_give_up(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    """A declared game after two tricks at which an opponent gave up through the API; the declarer's page, which
    plays through the page only, shows the request.
    """

    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
        table.play_out(CARDS_AFTER_TWO_TRICKS)
        table.declaring.step(opponents(table)[0], TABLE_GIVE_UP_SUFFIX)
        expect(table.pages[table.declarer_seat].locator(REQUEST)).to_be_visible()
        return table

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_opponents_give_up_shows_the_declarer_his_cards_held_and_the_two_answers(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_an_opponents_give_up(form_factor)
    asker = opponents(table)[0]
    declarer = table.pages[table.declarer_seat]

    expect(declarer.locator(REQUEST)).to_contain_text(gives_up(table.names[asker]))
    expect(button_of(declarer, ACCEPT)).to_be_visible()
    expect(button_of(declarer, PLAY_ON)).to_be_visible()
    expect(declarer.locator(HELD_CARDS)).to_be_visible()
    expect_nothing_to_overflow(declarer)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_declarers_yes_ends_the_game_on_every_page_with_the_result_and_no_request_and_no_card(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_an_opponents_give_up(form_factor)
    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(OWN_CARDS).first).to_be_visible()

    button_of(declarer, ACCEPT).click()

    for person in table.everyone:
        expect(person.locator(CARD)).to_be_visible()
        expect(person.locator(REQUEST)).to_have_count(0)
        expect(person.locator(OWN_CARDS)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_declarers_no_lets_the_hand_go_on_with_his_cards_lit_again(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_an_opponents_give_up(form_factor)
    declarer = table.pages[table.declarer_seat]

    button_of(declarer, PLAY_ON).click()

    expect_the_game_again(table)
    expect(declarer.locator(HELD_CARDS)).to_have_count(0)
    expect(declarer.locator(OWN_CARDS).first).to_be_visible()
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []
