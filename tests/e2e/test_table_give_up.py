from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.playing import TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable, button_of, reload_and_wait
from tests.e2e.support.early_end import THREE_SECONDS_MILLISECONDS, expect_a_refused_tap_to_show_the_failure_note
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, SMALL_PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.result_card import CARD, listed, waiting_for
from tests.e2e.support.table_menu import GIVE_UP_ROW, MENU, close_table_menu, menu_button, open_table_menu
from tests.e2e.support.tables import open_table_with_options

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
SHORTEN = text(SOURCE_LANGUAGE, "table.shorten")
PLAY_OPEN = text(SOURCE_LANGUAGE, "table.playOpen")
GIVE_UP_SURE = text(SOURCE_LANGUAGE, "table.giveUpSure")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
GIVEN_UP_STAMP = text(SOURCE_LANGUAGE, "result.givenUp")
NOTICE = ".notice"
NOTICE_SENTENCE = f"{NOTICE} .label"
NOTICE_MILLISECONDS = 4000
KEY = GIVE_UP_ROW
STRIP = ".actions"
BESIDE_THE_MENU = (4, 4)
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


def playing_on(names: list[str]) -> str:
    return text(SOURCE_LANGUAGE, "table.playingOn", names=listed(names))


def expect_no_refusal_notice(table: PlayingTable) -> None:
    for person in table.everyone:
        expect(person.locator(NOTICE, has_text=playing_on([]).strip())).to_have_count(0)


def expect_the_given_up_stamp(table: PlayingTable, giver_seat: int) -> None:
    for person in table.everyone:
        stamp = person.locator(f"{CARD} .stamp")
        expect(stamp).to_contain_text(GIVEN_UP_STAMP)
        expect(stamp.locator(".by")).to_have_text(table.names[giver_seat][0])


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
    expect_the_given_up_stamp(table, table.declarer_seat)
    expect_no_refusal_notice(table)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_two_nos_show_every_page_one_notice_with_both_faces_for_the_notice_time(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_request(form_factor)
    first, second = sorted(opponents(table))
    names = [table.names[first], table.names[second]]

    button_of(table.pages[first], PLAY_ON).click()
    expect(crossed(table.pages[second], first)).to_be_visible()
    button_of(table.pages[second], PLAY_ON).click()

    for person in table.everyone:
        notice = person.locator(NOTICE)
        expect(notice.locator(".label")).to_have_text(playing_on(names))
        expect(notice.locator(".dot")).to_have_text([name[0] for name in names])
        box = notice.bounding_box()
        viewport = person.viewport_size
        assert box is not None
        assert viewport is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]
    expect_the_game_again(table)
    for person in table.everyone:
        expect(person.locator(NOTICE)).to_have_count(0, timeout=3 * NOTICE_MILLISECONDS)
    assert page_errors == []


def test_a_reload_after_the_second_no_shows_no_notice(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_request(PHONE)
    first, second = opponents(table)
    button_of(table.pages[first], PLAY_ON).click()
    expect(crossed(table.pages[second], first)).to_be_visible()
    button_of(table.pages[second], PLAY_ON).click()
    expect(table.pages[first].locator(NOTICE)).to_be_visible()

    reload_and_wait(table.pages[first])

    expect_the_game_again(table)
    expect(table.pages[first].locator(NOTICE)).to_have_count(0)
    assert page_errors == []


def test_a_chair_that_changes_hands_after_the_first_no_shows_no_refusal(
    deal_a_request: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_request(PHONE)
    said_no, other = opponents(table)
    button_of(table.pages[said_no], PLAY_ON).click()
    expect(crossed(table.pages[other], said_no)).to_be_visible()

    table.stand_up_through_the_api(table.declarer_seat)

    stood_up = text(SOURCE_LANGUAGE, "table.standUpNotice", name=table.names[table.declarer_seat])
    for seat in (said_no, other):
        expect(table.pages[seat].locator(NOTICE_SENTENCE)).to_have_text(stood_up)
    expect_no_refusal_notice(table)
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
    expect_no_refusal_notice(table)
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
TRICK_CARDS = ".trick .face"


def expect_the_cards_played_to_have_reached(person: Page, played: int) -> None:
    """The person's page shows the last card played, so no newer version is left to put the armed key back."""
    expect(person.locator(OWN_CARDS)).to_have_count(10 - played // CARDS_AFTER_ONE_TRICK)
    expect(person.locator(TRICK_CARDS)).to_have_count(0)


class PartnerAgreesTable(DeclaringTable):
    """A table opened through the API whose special rule wants the partner's yes to an opponent's give-up."""

    def _open_table(
        self, opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember], *, running_points: bool
    ) -> str:
        assert not running_points
        return open_table_with_options(
            opener, server, RawSession(server, member_of(opener)), {"give_up": {"partner_agrees": True}}
        )


def partner_of(table: PlayingTable, opponent: int) -> int:
    (partner,) = (seat for seat in opponents(table) if seat != opponent)
    return partner


@pytest.fixture
def deal_an_opponents_give_up(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    """A declared game after two tricks at a table whose partner must agree, at which an opponent gave up through the
    API; his partner's page, which plays through the page only, shows the request.
    """

    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        table = deal_playing_table(
            open_person, e2e_server, member_of, page_errors, form_factor, declaring=PartnerAgreesTable
        )
        table.play_out(CARDS_AFTER_TWO_TRICKS)
        table.declaring.step(opponents(table)[0], TABLE_GIVE_UP_SUFFIX)
        expect(table.pages[partner_of(table, opponents(table)[0])].locator(REQUEST)).to_be_visible()
        return table

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_opponents_give_up_shows_his_partner_the_cards_held_and_the_two_answers_and_the_declarer_none(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_an_opponents_give_up(form_factor)
    asker = opponents(table)[0]
    partner = table.pages[partner_of(table, asker)]
    declarer = table.pages[table.declarer_seat]

    expect(partner.locator(REQUEST)).to_contain_text(wants_to_give_up(table.names[asker]))
    expect(button_of(partner, ACCEPT)).to_be_visible()
    expect(button_of(partner, PLAY_ON)).to_be_visible()
    expect(partner.locator(HELD_CARDS)).to_be_visible()
    expect(declarer.locator(REQUEST)).to_contain_text(wants_to_give_up(table.names[asker]))
    expect(declarer.locator(f"{REQUEST} button")).to_have_count(0)
    expect_nothing_to_overflow(partner)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_partners_yes_ends_the_game_on_every_page_with_the_result_and_no_request_and_no_card(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_an_opponents_give_up(form_factor)
    partner = table.pages[partner_of(table, opponents(table)[0])]
    expect(partner.locator(OWN_CARDS).first).to_be_visible()

    button_of(partner, ACCEPT).click()

    for person in table.everyone:
        expect(person.locator(CARD)).to_be_visible()
        expect(person.locator(REQUEST)).to_have_count(0)
        expect(person.locator(OWN_CARDS)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_partners_no_keeps_the_game_going_with_his_cards_lit_again(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_an_opponents_give_up(form_factor)
    partner = table.pages[partner_of(table, opponents(table)[0])]

    button_of(partner, PLAY_ON).click()

    expect_the_game_again(table)
    expect(partner.locator(HELD_CARDS)).to_have_count(0)
    expect(partner.locator(OWN_CARDS).first).to_be_visible()
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []


def test_after_a_yes_the_given_up_card_takes_the_next_hand_with_weiter(
    deal_an_opponents_give_up: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_an_opponents_give_up(PHONE)
    asker = opponents(table)[0]

    button_of(table.pages[partner_of(table, asker)], ACCEPT).click()

    expect_the_given_up_stamp(table, asker)
    for person in table.pages.values():
        person.locator(".actions").get_by_role("button", name=WEITER).click()
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    for person in table.pages.values():
        expect(person.locator(OWN_CARDS)).to_have_count(10)
    assert page_errors == []


def strip_keys(person: Page) -> list[str]:
    """The titles of the keys of the strip, left to right."""
    return person.locator(f"{STRIP} > .copy").evaluate_all("keys => keys.map(key => key.title || key.ariaLabel)")


def give_up_key(person: Page) -> Any:
    """The give-up row of the menu, which is opened first."""
    return open_table_menu(person).locator(KEY)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_seated_menu_holds_aufgeben_aufstehen_and_its_own_game_row_and_the_strip_and_the_watcher_have_none(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game(form_factor)

    for seat, person in table.pages.items():
        expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)
        expect(button_of(person, STAND_UP)).to_be_visible()
        expect(menu_button(person, SHORTEN if seat == table.declarer_seat else PLAY_OPEN)).to_be_visible()
        close_table_menu(person)
        assert strip_keys(person) == []
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(table.watcher.locator(KEY)).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", [SMALL_PHONE, DESKTOP], ids=["360", "1280"])
def test_the_armed_row_stays_inside_the_menu_and_the_menu_inside_the_page_without_scrolling(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_game({**form_factor, "groups": (AGENT_ADDERS_GROUP,)})
    person = table.pages[table.declarer_seat]

    give_up_key(person).click()

    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP_SURE)
    row = give_up_key(person).bounding_box()
    menu = person.locator(MENU).bounding_box()
    assert row is not None
    assert menu is not None
    assert menu["x"] <= row["x"]
    assert row["x"] + row["width"] <= menu["x"] + menu["width"]
    assert menu["x"] >= 0
    assert menu["x"] + menu["width"] <= form_factor["viewport"]["width"]
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


def test_a_tap_elsewhere_a_reload_and_a_newer_version_each_put_the_armed_key_back(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    person = table.pages[table.declarer_seat]

    give_up_key(person).click()
    person.mouse.click(*BESIDE_THE_MENU)
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)

    give_up_key(person).click()
    reload_and_wait(person)
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)

    give_up_key(person).click()
    table.play_out(1)
    expect(person.locator(".chair.turn")).not_to_have_attribute("data-seat", str(table.seat_at["forehand"]))
    expect(give_up_key(person)).to_have_attribute("title", GIVE_UP)
    assert page_errors == []


@pytest.mark.parametrize("played", [0, CARDS_AFTER_ONE_TRICK], ids=["ten cards", "nine cards"])
def test_the_declarers_second_tap_with_nine_or_ten_cards_ends_the_game_at_once_on_every_page(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str], played: int
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(played)
    declarer = table.pages[table.declarer_seat]
    expect_the_cards_played_to_have_reached(declarer, played)

    give_up_key(declarer).click()
    give_up_key(declarer).click()

    for person in table.everyone:
        expect(person.locator(CARD)).to_be_visible()
        expect(person.locator(REQUEST)).to_have_count(0)
    expect_the_given_up_stamp(table, table.declarer_seat)
    assert page_errors == []


def test_the_declarers_second_tap_with_fewer_cards_asks_the_opponents_with_the_request_plaque(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    declarer = table.pages[table.declarer_seat]
    expect_the_cards_played_to_have_reached(declarer, CARDS_AFTER_TWO_TRICKS)

    give_up_key(declarer).click()
    give_up_key(declarer).click()

    expect_the_request_without_a_no(table)
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []


def test_an_opponents_second_tap_ends_the_game_at_once_for_his_side_on_every_page_and_asks_nobody(
    deal_a_game: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_game(PHONE)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    asker = opponents(table)[0]
    expect_the_cards_played_to_have_reached(table.pages[asker], CARDS_AFTER_TWO_TRICKS)

    give_up_key(table.pages[asker]).click()
    give_up_key(table.pages[asker]).click()

    for person in table.everyone:
        expect(person.locator(CARD)).to_be_visible()
        expect(person.locator(REQUEST)).to_have_count(0)
    expect_the_given_up_stamp(table, asker)
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

    def tap_twice() -> None:
        give_up_key(declarer).click()
        give_up_key(declarer).click()

    expect_a_refused_tap_to_show_the_failure_note(
        declarer, f"{table.declaring.api_path}{TABLE_GIVE_UP_SUFFIX}", tap_twice
    )
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
        expect(person.locator(KEY)).to_have_count(0)
    assert page_errors == []
