from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.playing import TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import button_of, reload_and_wait
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, SMALL_PHONE, WIDTHS
from tests.e2e.support.result_card import CARD, waiting_for

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
GIVE_UP = text(SOURCE_LANGUAGE, "table.giveUp")
GIVE_UP_SURE = text(SOURCE_LANGUAGE, "table.giveUpSure")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
PILL = text(SOURCE_LANGUAGE, "agents.pill")
COPY_LINK = text(SOURCE_LANGUAGE, "table.copyLink")
KEY = ".copy.give-up"
STRIP = ".actions"
ROUND_KEY_PIXELS = 52
THREE_SECONDS_MILLISECONDS = 3000
CARDS_AFTER_ONE_TRICK = 3
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


@pytest.fixture
def deal_a_game(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    """A declared game before its first card, with the failure of a refused tap kept out of the console check."""

    def deal(form_factor: dict[str, Any], *, console: bool = True) -> PlayingTable:
        return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, console=console)

    return deal


def strip_keys(person: Page) -> list[str]:
    """The titles of the keys of the strip, left to right."""
    return person.locator(f"{STRIP} > .copy").evaluate_all("keys => keys.map(key => key.title || key.ariaLabel)")


def give_up_key(person: Page) -> Any:
    return person.locator(KEY)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_seated_bar_carries_aufgeben_first_and_a_round_aufstehen_beside_it_and_the_watcher_has_none(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game(form_factor)
    phone = form_factor["viewport"]["width"] < 900

    for person in table.pages.values():
        key = give_up_key(person)
        stand = button_of(person, STAND_UP)
        expect(key).to_have_attribute("title", GIVE_UP)
        assert strip_keys(person)[:2] == [GIVE_UP, STAND_UP]
        stand_box = stand.bounding_box()
        assert stand_box is not None
        assert (stand_box["width"] <= ROUND_KEY_PIXELS) is phone
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(give_up_key(table.watcher)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", [SMALL_PHONE, DESKTOP], ids=["360", "1280"])
def test_the_armed_key_beside_aufstehen_the_pill_and_the_link_stays_in_one_row_without_scrolling(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game({**form_factor, "groups": (AGENT_ADDERS_GROUP,)})
    person = table.pages[table.declarer_seat]

    give_up_key(person).click()

    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP_SURE)
    keys = [give_up_key(person), button_of(person, STAND_UP), button_of(person, PILL), button_of(person, COPY_LINK)]
    boxes = [key.bounding_box() for key in keys]
    assert None not in boxes
    assert len({box["y"] for box in boxes if box}) == 1, boxes
    assert max(box["x"] + box["width"] for box in boxes if box) <= form_factor["viewport"]["width"]
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page_errors == []


@pytest.mark.parametrize("motion", ["reduce", "no-preference"])
def test_the_first_tap_arms_the_key_with_a_run_out_line_that_moves_only_without_reduced_motion(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], motion: str
) -> None:
    table = deal_a_game({**PHONE, "reduced_motion": motion})
    person = table.pages[table.declarer_seat]

    give_up_key(person).click()

    run_out = person.locator(f"{KEY} .run-out")
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP_SURE)
    expect(run_out).to_have_count(1)
    expect(run_out).to_have_css("animation-name", "none" if motion == "reduce" else "run-out")
    assert table.view(table.declarer_seat)["hand"]["playing"]["give_up"] is None
    assert page_errors == []


def test_the_armed_key_runs_out_after_three_seconds_and_sends_nothing(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    person = table.pages[table.declarer_seat]

    give_up_key(person).click()

    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP_SURE)
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP, timeout=3 * THREE_SECONDS_MILLISECONDS)
    assert table.view(table.declarer_seat)["hand"]["playing"]["give_up"] is None
    assert page_errors == []


def test_a_tap_elsewhere_a_reload_a_card_and_a_newer_version_each_put_the_armed_key_back(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    person = table.pages[table.declarer_seat]
    opponent = opponents(table)[0]

    give_up_key(person).click()
    person.locator(".plaque").click()
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)

    give_up_key(person).click()
    reload_and_wait(person)
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)

    give_up_key(person).click()
    table.play_out(1)
    expect(person.locator(".chair.turn")).not_to_have_attribute("data-seat", str(table.seat_at["forehand"]))
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)

    give_up_key(person).click()
    table.declaring.step(opponent, TABLE_GIVE_UP_SUFFIX)
    expect(table.pages[table.declarer_seat].locator(REQUEST)).to_be_visible()
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)
    assert page_errors == []


@pytest.mark.parametrize("played", [0, CARDS_AFTER_ONE_TRICK], ids=["ten cards", "nine cards"])
def test_the_declarers_second_tap_with_nine_or_ten_cards_ends_the_game_at_once_on_every_page(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], played: int
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(played)
    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(OWN_CARDS)).to_have_count(10 - played // 3)

    give_up_key(declarer).click()
    give_up_key(declarer).click()

    for person in table.everyone:
        expect(person.locator(CARD)).to_be_visible()
        expect(person.locator(REQUEST)).to_have_count(0)
    assert page_errors == []


def test_the_declarers_second_tap_with_fewer_cards_asks_the_opponents_with_the_request_plaque(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(OWN_CARDS)).to_have_count(10 - CARDS_AFTER_TWO_TRICKS // 3)

    give_up_key(declarer).click()
    give_up_key(declarer).click()

    expect_the_request_without_a_no(table)
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []


def test_an_opponents_second_tap_gives_up_for_the_side_and_the_declarer_answers_it(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    asker = opponents(table)[0]
    expect(table.pages[asker].locator(OWN_CARDS)).to_have_count(10 - CARDS_AFTER_TWO_TRICKS // 3)

    give_up_key(table.pages[asker]).click()
    give_up_key(table.pages[asker]).click()

    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(REQUEST)).to_contain_text(gives_up(table.names[asker]))
    expect(button_of(declarer, ACCEPT)).to_be_visible()
    assert page_errors == []


def test_a_tap_while_the_request_of_the_other_side_stands_is_refused_and_shows_the_failure_note(
    deal_a_game: Callable[..., PlayingTable],
) -> None:
    # The browser logs the refused give-up as a console error; that refusal is the point of this test.
    table = deal_a_game(PHONE, console=False)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
    for person in table.everyone:
        expect(person.locator(REQUEST)).to_be_visible()
    opponent = table.pages[opponents(table)[0]]

    give_up_key(opponent).click()
    give_up_key(opponent).click()

    expect(opponent.locator(".note")).to_have_text(COMMAND_FAILED)
    expect(give_up_key(opponent)).to_be_enabled()
    expect_the_request_without_a_no(table)


def test_a_tap_that_the_table_refuses_shows_the_failure_note_and_offers_the_key_again(
    deal_a_game: Callable[..., PlayingTable],
) -> None:
    # The browser logs the refused give-up as a console error; that refusal is the point of this test.
    table = deal_a_game(PHONE, console=False)
    declarer = table.pages[table.declarer_seat]

    def refuse(route: Route) -> None:
        route.fulfill(status=409, content_type="application/json", body="{}")

    declarer.route(f"**{table.declaring.api_path}{TABLE_GIVE_UP_SUFFIX}", refuse)
    give_up_key(declarer).click()
    give_up_key(declarer).click()

    expect(declarer.locator(".note")).to_have_text(COMMAND_FAILED)
    expect(give_up_key(declarer)).to_be_enabled()
    expect(declarer.locator(CARD)).to_have_count(0)


def test_a_chair_left_open_takes_the_key_from_every_bar(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    standing = opponents(table)[0]
    others = [table.pages[seat] for seat in table.pages if seat != standing]

    table.stand_up_through_the_api(standing)

    for person in others:
        expect(person.locator(".chair.mine")).to_have_count(1)
        expect(give_up_key(person)).to_have_count(0)
    assert page_errors == []
