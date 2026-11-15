from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.playing import TABLE_SHORTEN_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable, button_of, reload_and_wait
from tests.e2e.support.early_end import (
    CARDS_AFTER_TWO_TRICKS,
    CROSS,
    NOTICE,
    NOTICE_MILLISECONDS,
    OPEN_CARDS,
    OPEN_TAG,
    REQUEST,
    SHORTEN_KEY,
    expect_nothing_to_overflow,
    expect_the_hand_and_the_strip_on_the_first_screen,
    expect_the_stamp,
    mark_on,
    opponents,
)
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.result_card import CARD, waiting_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

YES = text(SOURCE_LANGUAGE, "table.yes")
NO = text(SOURCE_LANGUAGE, "table.no")
SHORTEN = text(SOURCE_LANGUAGE, "table.shorten")
SAID_YES = text(SOURCE_LANGUAGE, "table.saidYes")
SAID_NO = text(SOURCE_LANGUAGE, "table.saidNo")
NO_ANSWER_YET = text(SOURCE_LANGUAGE, "table.noAnswerYet")
GIVE_UP = text(SOURCE_LANGUAGE, "table.giveUp")


@pytest.fixture
def deal_a_shortening(deal_a_game: Callable[..., PlayingTable]) -> Callable[..., PlayingTable]:
    """A declared game after two tricks at which the declarer shortened by the key on his page."""

    def deal(form_factor: dict[str, Any], *, console: bool = True) -> PlayingTable:
        table = deal_a_game(form_factor, console=console)
        table.play_out(CARDS_AFTER_TWO_TRICKS)
        declarer = table.pages[table.declarer_seat]
        expect(declarer.locator(SHORTEN_KEY)).to_be_enabled()
        declarer.locator(SHORTEN_KEY).click()
        for person in table.everyone:
            expect(person.locator(REQUEST)).to_be_visible()
        return table

    return deal


def wants_to_shorten(asker: str) -> str:
    return text(SOURCE_LANGUAGE, "table.wantsToShorten", name=asker)


def said_no_playing_on(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.saidNoPlayingOn", name=name)


def says(table: PlayingTable, seat: int, answer: str) -> None:
    button_of(table.pages[seat], answer).click()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_shortening_names_the_declarer_to_everyone_and_asks_each_opponent_yes_or_no(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_shortening(form_factor)
    asker = table.names[table.declarer_seat]
    first, second = opponents(table)

    for seat in (first, second):
        person = table.pages[seat]
        expect(person.locator(REQUEST)).to_contain_text(wants_to_shorten(asker))
        expect(button_of(person, YES)).to_be_visible()
        expect(button_of(person, NO)).to_be_visible()
    expect(table.watcher.locator(REQUEST)).to_contain_text(wants_to_shorten(asker))
    expect(table.watcher.locator(f"{REQUEST} button")).to_have_count(0)
    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(REQUEST)).to_contain_text(waiting_for([table.names[first], table.names[second]]))
    expect(declarer.locator(f"{REQUEST} button")).to_have_count(0)
    expect(declarer.locator(f".mark.unanswered[title='{NO_ANSWER_YET}']")).to_have_count(2)
    for person in table.everyone:
        expect(person.locator(OPEN_CARDS)).to_have_count(0)
        expect_nothing_to_overflow(person)
    assert page_errors == []


def test_both_opponents_saying_yes_ends_the_game_with_the_shortened_stamp_and_no_eyes(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_shortening(PHONE)
    first, second = opponents(table)

    says(table, first, YES)
    for person in table.everyone:
        expect(mark_on(person, first, ".mark.agreed")).to_have_attribute("title", SAID_YES)
    says(table, second, YES)

    expect_the_stamp(table, "result.shortened", table.declarer_seat)
    for person in table.everyone:
        expect(person.locator(f"{CARD} .points")).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_one_no_opens_the_declarers_cards_to_everyone_crosses_the_refuser_and_tells_that_play_goes_on(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_shortening(form_factor)
    refuser, other = opponents(table)

    says(table, refuser, NO)

    for seat, person in table.pages.items():
        if seat == table.declarer_seat:
            expect(person.locator(OPEN_TAG)).to_be_visible()
        else:
            expect(person.locator(OPEN_CARDS)).to_have_count(1)
        expect(person.locator(REQUEST)).to_have_count(0)
    expect(table.watcher.locator(OPEN_CARDS)).to_have_count(1)
    for person in table.everyone:
        expect(person.locator(NOTICE)).to_contain_text(said_no_playing_on(table.names[refuser]))
        expect(mark_on(person, refuser, CROSS)).to_have_attribute("title", SAID_NO)
        expect(mark_on(person, other, CROSS)).to_have_count(0)
        expect_nothing_to_overflow(person)
        expect_the_hand_and_the_strip_on_the_first_screen(person)
    for person in table.everyone:
        expect(person.locator(NOTICE)).to_have_count(0, timeout=3 * NOTICE_MILLISECONDS)
    assert page_errors == []


def test_a_reload_after_a_no_keeps_the_open_cards_and_the_cross_and_shows_no_notice(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_shortening(PHONE)
    refuser, _ = opponents(table)
    says(table, refuser, NO)
    expect(table.watcher.locator(NOTICE)).to_be_visible()

    for person in table.everyone:
        reload_and_wait(person)

    for person in table.everyone:
        expect(mark_on(person, refuser, CROSS)).to_be_visible()
        expect(person.locator(NOTICE)).to_have_count(0)
    expect(table.watcher.locator(OPEN_CARDS)).to_have_count(1)
    assert page_errors == []


def test_a_new_request_after_a_no_does_not_show_the_old_no(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_shortening(PHONE)
    refuser, other = opponents(table)
    declarer = table.pages[table.declarer_seat]
    says(table, refuser, NO)
    expect(mark_on(declarer, refuser, CROSS)).to_be_visible()

    expect(declarer.locator(SHORTEN_KEY)).to_be_enabled()
    declarer.locator(SHORTEN_KEY).click()

    for person in table.everyone:
        expect(person.locator(REQUEST)).to_be_visible()
        expect(person.locator(CROSS)).to_have_count(0)
    expect(declarer.locator(f".mark.unanswered[title='{NO_ANSWER_YET}']")).to_have_count(2)
    expect(table.pages[refuser].locator(REQUEST)).to_contain_text(wants_to_shorten(table.names[table.declarer_seat]))
    expect(button_of(table.pages[refuser], YES)).to_be_visible()
    expect(button_of(table.pages[other], NO)).to_be_visible()
    assert page_errors == []


def test_the_declarer_and_a_watcher_read_who_said_yes_and_who_is_awaited(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_shortening(PHONE)
    first, second = opponents(table)

    says(table, first, YES)

    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(REQUEST)).to_contain_text(waiting_for([table.names[second]]))
    expect(declarer.locator(f".mark.unanswered[title='{NO_ANSWER_YET}']")).to_have_count(1)
    watcher = table.watcher
    expect(watcher.locator(REQUEST)).to_contain_text(wants_to_shorten(table.names[table.declarer_seat]))
    expect(mark_on(watcher, first, ".mark.agreed")).to_be_visible()
    expect(mark_on(watcher, second, ".mark.unanswered")).to_be_visible()
    expect(watcher.locator(f"{REQUEST} button")).to_have_count(0)
    expect(button_of(table.pages[first], NO)).to_be_visible()
    expect(button_of(table.pages[first], YES)).to_have_count(0)
    expect(button_of(table.pages[second], YES)).to_be_visible()
    assert page_errors == []


def test_a_reload_in_every_role_and_a_reconnect_keep_the_standing_request(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    # The streams the test cuts are the console errors the browser logs, so only script errors are recorded; the
    # page's lazily loaded chunks still in flight when the connection is cut fail with it.
    expected_request_failures.extend([f"{e2e_server.base_url}{TABLES_PATH}/", f"{e2e_server.base_url}/_app/"])
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, PHONE, console=False)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    table.declaring.step(table.declarer_seat, TABLE_SHORTEN_SUFFIX)
    first, second = opponents(table)
    for person in table.everyone:
        expect(person.locator(REQUEST)).to_be_visible()

    for person in table.everyone:
        reload_and_wait(person)
        expect(person.locator(REQUEST)).to_be_visible()
    watcher = table.watcher
    watcher.context.set_offline(True)
    watcher.context.set_offline(False)

    asker = table.names[table.declarer_seat]
    expect(watcher.locator(REQUEST)).to_contain_text(wants_to_shorten(asker))
    expect(button_of(table.pages[first], YES)).to_be_visible()
    expect(button_of(table.pages[second], NO)).to_be_visible()
    expect(table.pages[table.declarer_seat].locator(REQUEST)).to_contain_text(
        waiting_for([table.names[first], table.names[second]])
    )


def test_a_card_takes_the_request_back_on_every_page(
    deal_a_shortening: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_shortening(PHONE)

    table.play_out(1)

    for person in table.everyone:
        expect(person.locator(REQUEST)).to_have_count(0)
        expect(person.locator(CROSS)).to_have_count(0)
    assert page_errors == []


def test_only_the_declarer_has_the_key_and_it_sits_before_aufgeben(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)

    declarer = table.pages[table.declarer_seat]
    keys = declarer.locator(f"{SHORTEN_KEY}, .copy.give-up").evaluate_all("keys => keys.map(key => key.title)")
    assert keys == [SHORTEN, GIVE_UP]
    expect(declarer.locator(SHORTEN_KEY)).to_have_count(1)
    for seat in opponents(table):
        expect(table.pages[seat].locator(SHORTEN_KEY)).to_have_count(0)
    expect(table.watcher.locator(SHORTEN_KEY)).to_have_count(0)
    assert page_errors == []


def test_no_key_while_the_declarer_still_declares_or_a_chair_is_open_or_a_request_stands(
    deal_a_declaring_table: Callable[..., DeclaringTable], deal_a_game: Callable[..., PlayingTable]
) -> None:
    declaring = deal_a_declaring_table(PHONE)
    expect(declaring.declarer.locator(".chair.mine")).to_have_count(1)
    expect(declaring.declarer.locator(SHORTEN_KEY)).to_have_count(0)

    table = deal_a_game(PHONE)
    standing = opponents(table)[0]
    table.stand_up_through_the_api(standing)

    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(".chair.mine")).to_have_count(1)
    expect(declarer.locator(SHORTEN_KEY)).to_have_count(0)
    expect(declarer.locator(".copy.give-up")).to_have_count(0)
