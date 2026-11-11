from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.tables import TABLE_SIT_SUFFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.tables import SIT_DOWN, assert_never_reloaded, mark_page, open_new_table, plate_of, sit_in, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SEAT_TAKEN = text(SOURCE_LANGUAGE, "table.seatTaken")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
SEAT_AWAY = text(SOURCE_LANGUAGE, "table.seatAway")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
# The page hides its notice after a few seconds.
NOTICE_GONE_TIMEOUT_MILLISECONDS = 10_000
SEAT_BUTTON = "button.tile.free"


def watchers_of(person: Page):
    return person.locator(".watchers span")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_watcher_sits_and_stands_and_every_open_page_follows_without_a_reload(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    sitter = record_page_errors(open_person(username="ben", **form_factor), page_errors)
    watch(sitter, e2e_server, path)
    onlooker = record_page_errors(open_person(username="cleo", **form_factor), page_errors)
    watch(onlooker, e2e_server, path)
    pages = (opener, sitter, onlooker)
    for person in pages:
        mark_page(person)
        expect(watchers_of(person)).to_have_text("2")
    expect(opener.get_by_role("button", name=SIT_DOWN)).to_have_count(0)

    sit_in(sitter, 2)

    for person in (opener, onlooker):
        expect(plate_of(person, 2)).to_have_text("ben")
    expect(plate_of(sitter, 2)).to_have_text(YOU)
    for person in pages:
        expect(watchers_of(person)).to_have_text("1")
    expect(sitter.get_by_role("button", name=STAND_UP)).to_be_visible()
    expect(sitter.get_by_role("button", name=SIT_DOWN)).to_have_count(0)
    expect(onlooker.get_by_role("button", name=STAND_UP)).to_have_count(0)

    sitter.get_by_role("button", name=STAND_UP).click()

    for person in pages:
        expect(plate_of(person, 2)).to_have_text(SEAT_FREE)
        expect(watchers_of(person)).to_have_text("2")
    expect(sitter.get_by_role("button", name=SIT_DOWN)).to_have_count(2)
    assert_never_reloaded(*pages)


def test_three_sit_and_a_fourth_member_only_watches_while_the_hand_runs(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    second = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(second, e2e_server, path)
    sit_in(second, 2)
    expect(plate_of(opener, 2)).to_have_text("ben")
    second.get_by_role("button", name=STAND_UP).click()
    expect(plate_of(opener, 2)).to_have_text(SEAT_FREE)
    sit_in(second, 2)
    third = record_page_errors(open_person(username="cleo", **DESKTOP), page_errors)
    watch(third, e2e_server, path)
    sit_in(third, 3)
    fourth = record_page_errors(open_person(username="dora", **DESKTOP), page_errors)

    watch(fourth, e2e_server, path)

    for seat, name in ((1, "anna"), (2, "ben"), (3, "cleo")):
        expect(plate_of(fourth, seat)).to_have_text(name)
    expect(fourth.get_by_role("button", name=SIT_DOWN)).to_have_count(0)
    expect(fourth.get_by_role("button", name=STAND_UP)).to_have_count(0)
    expect(watchers_of(fourth)).to_have_text("1")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_seated_member_who_closes_the_page_shows_as_away_until_the_page_opens_again(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    onlooker = record_page_errors(open_person(username="ben", **form_factor), page_errors)
    watch(onlooker, e2e_server, path)
    mark_page(onlooker)
    anna_chair = onlooker.locator(".chair[data-seat='1']")
    expect(anna_chair.locator(".mark.away")).to_have_count(0)

    returning = record_page_errors(opener.context.new_page(), page_errors)
    opener.close()

    expect(anna_chair.locator(".mark.away")).to_be_visible()
    expect(plate_of(onlooker, 1)).to_contain_text(SEAT_AWAY)
    expect(plate_of(onlooker, 1)).to_contain_text("anna")
    assert onlooker.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    watch(returning, e2e_server, path)

    expect(anna_chair.locator(".mark.away")).to_have_count(0)
    expect(plate_of(onlooker, 1)).to_have_text("anna")
    expect(returning.locator(".mark.away")).to_have_count(0)
    assert_never_reloaded(onlooker)


def lose_the_last_chair(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    *,
    holder_name: str,
    loser_form: dict[str, Any],
) -> Page:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    second = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(second, e2e_server, path)
    sit_in(second, 2)
    winner = record_page_errors(open_person(username=holder_name, **DESKTOP), page_errors)
    # The browser logs every 409 as a console error; the loser's refusal is the point of these tests.
    loser = record_page_errors(open_person(username="dora", **loser_form), page_errors, console=False)
    watch(winner, e2e_server, path)
    watch(loser, e2e_server, path)

    def let_the_winner_sit_first(route: Route) -> None:
        sit_in(winner, 3)
        expect(plate_of(winner, 3)).to_have_text(YOU)
        route.continue_()

    loser.route(f"**{TABLES_PATH}/*{TABLE_SIT_SUFFIX}", let_the_winner_sit_first)

    sit_in(loser, 3)
    return loser


def test_two_browsers_taking_the_last_chair_seat_one_and_the_other_is_told_who_got_it(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    page_errors: list[str],
) -> None:
    loser = lose_the_last_chair(open_person, e2e_server, page_errors, holder_name="cleo", loser_form=DESKTOP)

    notice = loser.locator(".notice")
    expect(notice).to_contain_text(SEAT_TAKEN)
    expect(notice).to_contain_text("cleo")
    expect(plate_of(loser, 3)).to_have_text("cleo")
    expect(loser.get_by_role("button", name=SIT_DOWN)).to_have_count(0)
    expect(notice).to_be_hidden(timeout=NOTICE_GONE_TIMEOUT_MILLISECONDS)


@pytest.mark.parametrize("holder_name", ["W" * 64, "Maximilian-Alexander-Bartholomaeus-von-Hohenzollern-Sigmaringen"])
def test_the_taken_notice_keeps_its_label_on_one_line_when_the_holder_name_is_long(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    page_errors: list[str],
    holder_name: str,
) -> None:
    loser = lose_the_last_chair(open_person, e2e_server, page_errors, holder_name=holder_name, loser_form=SMALL_PHONE)

    expect(loser.locator(".notice")).to_contain_text(SEAT_TAKEN)
    label_is_one_line = loser.evaluate(
        "() => { const label = document.querySelector('.notice .label');"
        " return label.getBoundingClientRect().height < 1.6 * parseFloat(getComputedStyle(label).fontSize); }"
    )
    assert label_is_one_line is True
    assert loser.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_a_command_that_cannot_be_sent_says_so_and_changes_nothing(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
    page_errors: list[str],
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    sitter = record_page_errors(open_person(username="ben", **DESKTOP), page_errors, console=False)
    watch(sitter, e2e_server, path)
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    sitter.route(f"**{TABLES_PATH}/*{TABLE_SIT_SUFFIX}", lambda route: route.abort())

    sit_in(sitter, 2)

    expect(sitter.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    expect(plate_of(sitter, 2)).to_have_text(SEAT_FREE)
    expect(plate_of(opener, 2)).to_have_text(SEAT_FREE)
