from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.playing import TABLE_PLAY_OPEN_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable, button_of, reload_and_wait
from tests.e2e.support.early_end import (
    CARDS_AFTER_TWO_TRICKS,
    NOTICE,
    NOTICE_MILLISECONDS,
    OPEN_CARDS,
    OPEN_TAG,
    OWN_CARDS,
    PLAY_OPEN_KEY,
    REQUEST,
    STRIP,
    THREE_SECONDS_MILLISECONDS,
    expect_a_refused_tap_to_show_the_failure_note,
    expect_nothing_to_overflow,
    expect_the_hand_and_the_strip_on_the_first_screen,
    expect_the_stamp,
    mark_on,
    opponents,
)
from tests.e2e.support.people import PHONE, SMALL_PHONE, WIDTHS
from tests.e2e.support.result_card import waiting_for
from tests.e2e.support.server import AlwaysTheSameDeal, skat_on_new_database

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

# The deal this module's server draws, with Kreuz declared by the middlehand and every seat playing its first legal
# card, leaves the declarer no trick once these cards are played, so an open play is right then and wrong before.
DEAL_WITH_A_RIGHT_OPEN_PLAY_AT_THE_END = 5
CARDS_AT_WHICH_OPEN_PLAY_IS_RIGHT = 27

ACCEPT = text(SOURCE_LANGUAGE, "table.accept")
PLAY_ON = text(SOURCE_LANGUAGE, "table.playOn")
PLAY_OPEN = text(SOURCE_LANGUAGE, "table.playOpen")
PLAY_OPEN_SURE = text(SOURCE_LANGUAGE, "table.playOpenSure")
YOU_PLAY_OPEN = text(SOURCE_LANGUAGE, "table.youPlayOpen")
OPEN_MARK = text(SOURCE_LANGUAGE, "table.playsOpenMark")
NO_ANSWER_YET = text(SOURCE_LANGUAGE, "table.noAnswerYet")


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, which deals every hand as one whose open play is wrong early and right at the end."""
    random_source = AlwaysTheSameDeal(DEAL_WITH_A_RIGHT_OPEN_PLAY_AT_THE_END)
    with skat_on_new_database(tmp_path_factory, random_source=random_source) as server:
        yield server


@pytest.fixture
def deal_a_wrong_open_play(deal_a_game: Callable[..., PlayingTable]) -> Callable[..., PlayingTable]:
    """A declared game after two tricks at which an opponent played open by the key on his page, wrongly."""

    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        table = deal_a_game(form_factor)
        table.play_out(CARDS_AFTER_TWO_TRICKS)
        player = table.pages[opponents(table)[0]]
        expect(player.locator(OWN_CARDS)).to_have_count(8)
        play_open_through_the_key(player)
        for person in table.everyone:
            expect(person.locator(REQUEST)).to_be_visible()
        return table

    return deal


def play_open_through_the_key(person: Page) -> None:
    key = person.locator(PLAY_OPEN_KEY)
    expect(key).to_be_enabled()
    key.click()
    expect(key).to_have_attribute("title", PLAY_OPEN_SURE)
    key.click()


def plays_open(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.playsOpen", name=name)


def plays_open_on(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.playsOpenOn", name=name)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_wrong_open_play_asks_the_declarer_to_accept_or_play_on_and_shows_the_others_who_is_awaited(
    deal_a_wrong_open_play: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_wrong_open_play(form_factor)
    player, other = opponents(table)
    declarer = table.pages[table.declarer_seat]

    expect(declarer.locator(REQUEST)).to_contain_text(plays_open(table.names[player]))
    expect(button_of(declarer, ACCEPT)).to_be_visible()
    expect(button_of(declarer, PLAY_ON)).to_be_visible()
    asker = table.pages[player]
    expect(asker.locator(REQUEST)).to_contain_text(YOU_PLAY_OPEN)
    expect(asker.locator(REQUEST)).to_contain_text(waiting_for([table.names[table.declarer_seat]]))
    expect(asker.locator(f"{REQUEST} button")).to_have_count(0)
    expect(asker.locator(f".mark.unanswered[title='{NO_ANSWER_YET}']")).to_have_count(1)
    for person in (table.pages[other], table.watcher):
        expect(person.locator(REQUEST)).to_contain_text(plays_open(table.names[player]))
        expect(person.locator(f"{REQUEST} button")).to_have_count(0)
    for person in table.everyone:
        expect(person.locator(OPEN_CARDS)).to_have_count(0)
        expect_nothing_to_overflow(person)
    assert page_errors == []


def test_the_declarers_accept_ends_the_game_with_the_played_open_stamp_of_the_opponent(
    deal_a_wrong_open_play: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_wrong_open_play(PHONE)
    player, _ = opponents(table)

    button_of(table.pages[table.declarer_seat], ACCEPT).click()

    expect_the_stamp(table, "result.playedOpen", player)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_declarers_play_on_opens_that_opponents_cards_for_everyone_with_the_eye_and_a_notice(
    deal_a_wrong_open_play: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_wrong_open_play(form_factor)
    player, other = opponents(table)

    button_of(table.pages[table.declarer_seat], PLAY_ON).click()

    for seat, person in table.pages.items():
        expect(person.locator(REQUEST)).to_have_count(0)
        if seat == player:
            expect(person.locator(OPEN_TAG)).to_be_visible()
            expect(person.locator(OPEN_CARDS)).to_have_count(0)
        else:
            expect(person.locator(OPEN_CARDS)).to_have_count(1)
    expect(table.watcher.locator(OPEN_CARDS)).to_have_count(1)
    expect(table.watcher.locator(f".chair[data-seat='{other}'] .fan-spot")).to_have_count(1)
    expect(table.watcher.locator(f".chair[data-seat='{table.declarer_seat}'] .fan-spot")).to_have_count(1)
    for person in table.everyone:
        expect(person.locator(NOTICE)).to_contain_text(plays_open_on(table.names[player]))
        expect(mark_on(person, player, ".mark.open-play")).to_have_attribute("title", OPEN_MARK)
        expect_nothing_to_overflow(person)
        expect_the_hand_and_the_strip_on_the_first_screen(person)
    for person in table.everyone:
        expect(person.locator(NOTICE)).to_have_count(0, timeout=3 * NOTICE_MILLISECONDS)
    assert page_errors == []


def test_a_reload_keeps_the_standing_request_and_the_open_cards_after_playing_on(
    deal_a_wrong_open_play: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_wrong_open_play(PHONE)
    player, _ = opponents(table)
    for person in table.everyone:
        reload_and_wait(person)
        expect(person.locator(REQUEST)).to_contain_text(
            plays_open(table.names[player]) if person is not table.pages[player] else YOU_PLAY_OPEN
        )
    button_of(table.pages[table.declarer_seat], PLAY_ON).click()
    expect(table.watcher.locator(OPEN_CARDS)).to_have_count(1)

    for person in table.everyone:
        reload_and_wait(person)

    expect(table.watcher.locator(OPEN_CARDS)).to_have_count(1)
    for person in table.everyone:
        expect(mark_on(person, player, ".mark.open-play")).to_be_visible()
        expect(person.locator(NOTICE)).to_have_count(0)
    assert page_errors == []


def test_a_reconnect_keeps_the_standing_request_for_a_watcher(
    deal_a_game: Callable[..., PlayingTable],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    # The streams the test cuts are the console errors the browser logs, so only script errors are recorded.
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    table = deal_a_game(PHONE, console=False)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    player, _ = opponents(table)
    expect(table.pages[player].locator(OWN_CARDS)).to_have_count(8)
    play_open_through_the_key(table.pages[player])
    watcher = table.watcher
    expect(watcher.locator(REQUEST)).to_contain_text(plays_open(table.names[player]))

    watcher.context.set_offline(True)
    watcher.context.set_offline(False)

    expect(watcher.locator(REQUEST)).to_contain_text(plays_open(table.names[player]))
    expect(button_of(table.pages[table.declarer_seat], PLAY_ON)).to_be_visible()
    assert page_errors == []


def test_a_right_open_play_ends_the_game_with_the_played_open_stamp_of_the_opponent(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(CARDS_AT_WHICH_OPEN_PLAY_IS_RIGHT)
    player = table.pages[opponents(table)[0]]
    expect(player.locator(OWN_CARDS)).to_have_count(1)

    play_open_through_the_key(player)

    expect_the_stamp(table, "result.playedOpen", opponents(table)[0])
    for person in table.everyone:
        expect(person.locator(".result .points")).to_have_count(1)
    assert page_errors == []


def test_the_key_sends_nothing_before_its_second_tap(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    player = table.pages[opponents(table)[0]]
    key = player.locator(PLAY_OPEN_KEY)
    sent: list[str] = []
    player.on(
        "request", lambda request: sent.append(request.url) if request.url.endswith(TABLE_PLAY_OPEN_SUFFIX) else None
    )

    key.click()

    expect(key).to_have_attribute("title", PLAY_OPEN_SURE)
    expect(key).to_have_attribute("title", PLAY_OPEN, timeout=3 * THREE_SECONDS_MILLISECONDS)
    assert sent == []
    assert page_errors == []


def test_only_an_opponent_has_the_key_and_it_sits_before_aufgeben_and_a_chair_left_open_takes_it(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    first, second = opponents(table)

    for seat in (first, second):
        keys = (
            table.pages[seat]
            .locator(f"{PLAY_OPEN_KEY}, .copy.give-up")
            .evaluate_all("keys => keys.map(key => key.title)")
        )
        assert keys == [PLAY_OPEN, text(SOURCE_LANGUAGE, "table.giveUp")]
    expect(table.pages[table.declarer_seat].locator(PLAY_OPEN_KEY)).to_have_count(0)
    expect(table.watcher.locator(PLAY_OPEN_KEY)).to_have_count(0)

    table.stand_up_through_the_api(first)

    expect(table.pages[second].locator(".chair.mine")).to_have_count(1)
    expect(table.pages[second].locator(PLAY_OPEN_KEY)).to_have_count(0)
    assert page_errors == []


def test_no_key_for_an_opponent_while_the_declarer_still_declares(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str]
) -> None:
    declaring = deal_a_declaring_table(PHONE)

    for opponent in declaring.others:
        expect(opponent.locator(".chair.mine")).to_have_count(1)
        expect(opponent.locator(PLAY_OPEN_KEY)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", [SMALL_PHONE, PHONE])
def test_the_strip_with_the_key_stays_one_row_without_scrolling_also_armed(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game(form_factor)
    for person in (table.pages[opponents(table)[0]], table.pages[table.declarer_seat]):
        keys = person.locator(".actions > .copy").all()
        tops = {round(box["y"]) for key in keys if (box := key.bounding_box()) is not None}
        assert len(tops) == 1
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    opponent = table.pages[opponents(table)[0]]
    armed = opponent.locator(PLAY_OPEN_KEY)
    armed.click()
    expect(armed).to_have_attribute("title", PLAY_OPEN_SURE)
    expect_nothing_to_overflow(opponent, f"{STRIP} > :not([popover])")
    assert page_errors == []


def test_a_second_tap_that_the_table_refuses_shows_the_failure_note_and_offers_the_key_again(
    deal_a_game: Callable[..., PlayingTable],
) -> None:
    # The browser logs the refused open play as a console error; that refusal is the point of this test.
    table = deal_a_game(PHONE, console=False)
    player = table.pages[opponents(table)[0]]

    expect_a_refused_tap_to_show_the_failure_note(
        player,
        f"{table.declaring.api_path}{TABLE_PLAY_OPEN_SUFFIX}",
        lambda: play_open_through_the_key(player),
    )
    expect(player.locator(PLAY_OPEN_KEY)).to_be_enabled()
    expect(player.locator(REQUEST)).to_have_count(0)
