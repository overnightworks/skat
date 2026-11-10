import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect
from sqlalchemy import text

from skat.table.records import SERIES_LENGTH_DEFAULT, SERIES_LENGTH_MAX, SERIES_LENGTH_MIN, SERIES_LENGTH_STEP
from skat.web.constants import ACCOUNT_PATH, LOGIN_PATH
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors, sign_in_at_issuer
from tests.e2e.support.people import DESKTOP, FORM_FACTORS, WIDTHS
from tests.e2e.support.tables import OPEN_TABLE, TABLE_URL, click_new_table, open_new_table, table_id_of
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e


TABLES_ROUTE = f"**{TABLES_PATH}"
UNKNOWN_ID = "0" * 32
SERVER_ERROR = 500
OK = 200
UNAUTHORIZED = 401


def table_count(server: RunningServer) -> int:
    with server.engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM tables")).scalar_one())


def same_origin(server: RunningServer) -> dict[str, str]:
    """The headers of a fetch from Skat's own page, which the origin check admits."""
    return {"origin": server.base_url, "accept": "application/json"}


def expect_a_table_seating(person: Page, opener: str, *, mine: bool) -> None:
    expect(person.get_by_text(catalog_text("waitingForPlayers"))).to_be_visible()
    expect(person.get_by_role("button", name=catalog_text("copyLink"))).to_be_visible()
    chairs = person.locator(".chair")
    expect(chairs).to_have_count(3)
    expect(person.locator(".chair[data-seat='1'] .plate")).to_have_text(opener)
    expect(person.locator(".chair.mine")).to_have_count(1 if mine else 0)
    expect(person.locator(".chair .plate", has_text=catalog_text("seatFree"))).to_have_count(2)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_member_opens_a_table_and_sits_in_chair_one_with_two_free_chairs(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    before = table_count(e2e_server)

    open_new_table(person, e2e_server)

    expect_a_table_seating(person, "anna", mine=True)
    assert table_count(e2e_server) == before + 1
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert person.evaluate("document.querySelector('.chair.mine').getBoundingClientRect().top") > person.evaluate(
        "document.querySelector('.chair:not(.mine)').getBoundingClientRect().top"
    )


def a_sheet(person: Page, server: RunningServer) -> None:
    person.goto(f"{server.base_url}/")
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()


def series_length_reading(length: int) -> str:
    return f"{length} {catalog_text('seriesGames')}"


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_sheet_offers_the_default_series_length_in_steps_and_stops_at_both_ends(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    fewer = person.get_by_role("button", name=catalog_text("seriesFewer"))
    more = person.get_by_role("button", name=catalog_text("seriesMore"))
    reading = person.get_by_role("spinbutton", name=catalog_text("seriesGames"))

    a_sheet(person, e2e_server)

    expect(person.get_by_role("dialog")).to_be_visible()
    expect(reading).to_have_text(series_length_reading(SERIES_LENGTH_DEFAULT), use_inner_text=True)
    fewer.click()
    expect(reading).to_have_text(series_length_reading(SERIES_LENGTH_DEFAULT - SERIES_LENGTH_STEP), use_inner_text=True)
    for _ in range((SERIES_LENGTH_DEFAULT - SERIES_LENGTH_MIN) // SERIES_LENGTH_STEP - 1):
        fewer.click()
    expect(reading).to_have_text(series_length_reading(SERIES_LENGTH_MIN), use_inner_text=True)
    expect(fewer).to_be_disabled()
    for _ in range((SERIES_LENGTH_MAX - SERIES_LENGTH_MIN) // SERIES_LENGTH_STEP):
        more.click()
    expect(reading).to_have_text(series_length_reading(SERIES_LENGTH_MAX), use_inner_text=True)
    expect(more).to_be_disabled()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_sheet_fits_inside_the_screen(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)

    a_sheet(person, e2e_server)

    expect(person.get_by_role("dialog")).to_be_visible()
    box = person.get_by_role("dialog").bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= form_factor["viewport"]["height"]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_sheet_reopened_after_cancelling_reads_the_default_length_again(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    a_sheet(person, e2e_server)
    person.get_by_role("button", name=catalog_text("seriesFewer")).click()

    person.get_by_role("button", name=catalog_text("cancelNewTable")).click()
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    expect(person.get_by_role("spinbutton", name=catalog_text("seriesGames"))).to_have_text(
        series_length_reading(SERIES_LENGTH_DEFAULT), use_inner_text=True
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_opens_with_the_chosen_length_in_one_request_even_when_the_button_is_double_tapped(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    requests: list[str] = []
    person.on("request", lambda request: requests.append(request.post_data or "") if request.method == "POST" else None)
    before = table_count(e2e_server)
    a_sheet(person, e2e_server)
    for _ in range(2):
        person.get_by_role("button", name=catalog_text("seriesFewer")).click()

    person.get_by_role("button", name=OPEN_TABLE).dblclick()

    expect(person).to_have_url(TABLE_URL)
    assert len(requests) == 1
    assert '"series_length":30' in requests[0]
    answer = person.request.get(f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(urlsplit(person.url).path)}")
    series = answer.json()["series"]
    assert (series["game_number"], series["game_count"], series["over"]) == (0, 30, False)
    assert table_count(e2e_server) == before + 1


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_cancelling_the_sheet_closes_it_and_sends_nothing(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    requests: list[str] = []
    person.on("request", lambda request: requests.append(request.url) if request.method == "POST" else None)
    before = table_count(e2e_server)
    a_sheet(person, e2e_server)

    person.get_by_role("button", name=catalog_text("cancelNewTable")).click()

    expect(person.get_by_role("dialog")).to_have_count(0)
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    assert requests == []
    assert table_count(e2e_server) == before


def test_a_reload_shows_the_same_table_with_the_opener_still_in_chair_one(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(person, e2e_server)

    person.reload()

    expect(person).to_have_url(f"{e2e_server.base_url}{path}")
    expect_a_table_seating(person, "anna", mine=True)


def test_another_member_opening_the_link_sees_the_opener_in_chair_one_and_no_chair_of_their_own(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    visitor = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)

    visitor.goto(f"{e2e_server.base_url}{path}")

    expect_a_table_seating(visitor, "anna", mine=False)


def test_a_member_may_open_any_number_of_tables_each_under_a_link_of_its_own(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    before = table_count(e2e_server)

    first = open_new_table(person, e2e_server)
    person.get_by_role("link", name="Skat", exact=True).click()
    second = click_new_table(person)

    assert first != second
    assert table_count(e2e_server) == before + 2


@pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-a-table", "%27%3B--"])
def test_an_unknown_or_malformed_id_shows_not_found_and_offers_a_new_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], table_id: str
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{table_id}")

    expect(person.get_by_role("heading", name=catalog_text("tableNotFound"))).to_be_visible()
    expect(person.get_by_text(re.compile("error|sql|postgres", re.IGNORECASE))).to_have_count(0)
    click_new_table(person)

    expect_a_table_seating(person, "anna", mine=True)


def test_the_link_control_copies_the_absolute_link_of_the_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    person.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=e2e_server.base_url)
    path = open_new_table(person, e2e_server)

    person.get_by_role("button", name=catalog_text("copyLink")).click()

    expect(person.get_by_role("status")).to_have_text(catalog_text("linkCopied"))
    assert person.evaluate("navigator.clipboard.readText()") == f"{e2e_server.base_url}{path}"


def test_a_refused_copy_says_so(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    open_new_table(person, e2e_server)
    person.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('refused')); }")

    person.get_by_role("button", name=catalog_text("copyLink")).click()

    expect(person.get_by_role("status")).to_have_text(catalog_text("linkCopyFailed"))


def test_a_late_not_found_answer_does_not_replace_the_table_the_address_shows(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    held: list[Route] = []

    def hold_the_first_read(route: Route) -> None:
        if held:
            route.continue_()
        else:
            held.append(route)

    person.goto(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{UNKNOWN_ID}")
    expect(person.get_by_role("heading", name=catalog_text("tableNotFound"))).to_be_visible()
    click_new_table(person)
    expect_a_table_seating(person, "anna", mine=True)
    person.route(f"**{TABLES_PATH}/{UNKNOWN_ID}", hold_the_first_read)

    person.go_back()
    expect(person).to_have_url(re.compile(f"{UNKNOWN_ID}$"))
    person.go_forward()
    expect(person).to_have_url(TABLE_URL)
    expect_a_table_seating(person, "anna", mine=True)
    with person.expect_response(re.compile(f"{UNKNOWN_ID}$")):
        held[0].continue_()
    # Two frames let the page act on the answer it just received.
    person.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")

    expect_a_table_seating(person, "anna", mine=True)
    expect(person.get_by_role("heading", name=catalog_text("tableNotFound"))).to_have_count(0)


def test_a_table_the_server_cannot_read_says_so(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    person.route(f"**{TABLES_PATH}/*", lambda route: route.fulfill(status=SERVER_ERROR, body="{}"))

    person.goto(f"{e2e_server.base_url}{path}")

    expect(person.get_by_role("alert")).to_contain_text(catalog_text("tableLoadFailed"))


@pytest.mark.parametrize("failure", ["server error", "lost connection", "unreadable answer"])
def test_a_table_that_could_not_be_opened_says_so_and_a_retry_opens_it(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
    failure: str,
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}")
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    attempts: list[str] = []

    def fail_the_first_attempt(route: Route) -> None:
        attempts.append(route.request.post_data or "")
        if len(attempts) > 1:
            route.continue_()
        elif failure == "server error":
            route.fulfill(status=SERVER_ERROR, body="{}")
        elif failure == "lost connection":
            # The server opens the table; only its answer is lost.
            route.fetch()
            route.abort()
        else:
            # The server opens the table; its answer arrives with a body that cannot be read.
            route.fetch()
            route.fulfill(status=OK, body="{")

    person.route(TABLES_ROUTE, fail_the_first_attempt)
    before = table_count(e2e_server)
    person.goto(f"{e2e_server.base_url}/")

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person.get_by_role("alert")).to_have_text(catalog_text("newTableFailed"))
    person.get_by_role("button", name=OPEN_TABLE).click()

    expect(person).to_have_url(TABLE_URL)
    assert attempts[0] == attempts[1]
    assert table_count(e2e_server) == before + 1


def lose_the_first_answer_of_opening_a_table(person: Page) -> list[dict[str, Any]]:
    """Routes the table request so the server opens the table but its first answer is lost; returns every attempt."""
    attempts: list[dict[str, Any]] = []

    def lose_the_first_answer(route: Route) -> None:
        attempts.append(json.loads(route.request.post_data or "{}"))
        if len(attempts) > 1:
            route.continue_()
        else:
            route.fetch()
            route.abort()

    person.route(TABLES_ROUTE, lose_the_first_answer)
    return attempts


def test_a_length_changed_after_a_lost_answer_opens_a_table_at_the_new_length(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}")
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    attempts = lose_the_first_answer_of_opening_a_table(person)
    a_sheet(person, e2e_server)
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person.get_by_role("alert")).to_have_text(catalog_text("newTableFailed"))

    person.get_by_role("button", name=catalog_text("seriesFewer")).click()
    person.get_by_role("button", name=OPEN_TABLE).click()

    expect(person).to_have_url(TABLE_URL)
    answer = person.request.get(f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(urlsplit(person.url).path)}")
    assert (
        answer.json()["series"]["game_count"]
        == attempts[1]["series_length"]
        == attempts[0]["series_length"] - SERIES_LENGTH_STEP
    )
    assert attempts[1]["command_id"] != attempts[0]["command_id"]


@pytest.mark.parametrize("steps_before_the_lost_answer", [0, 1])
def test_a_sheet_reopened_after_a_lost_answer_replays_the_lost_table_unless_the_length_was_stepped(
    steps_before_the_lost_answer: int,
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}")
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors, console=False)
    attempts = lose_the_first_answer_of_opening_a_table(person)
    before = table_count(e2e_server)
    a_sheet(person, e2e_server)
    for _ in range(steps_before_the_lost_answer):
        person.get_by_role("button", name=catalog_text("seriesFewer")).click()
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person.get_by_role("alert")).to_have_text(catalog_text("newTableFailed"))

    person.get_by_role("button", name=catalog_text("cancelNewTable")).click()
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    person.get_by_role("button", name=OPEN_TABLE).click()

    expect(person).to_have_url(TABLE_URL)
    if steps_before_the_lost_answer:
        assert attempts[1]["series_length"] == attempts[0]["series_length"] + SERIES_LENGTH_STEP
        assert attempts[1]["command_id"] != attempts[0]["command_id"]
    else:
        assert attempts[1] == attempts[0]
        assert table_count(e2e_server) == before + 1


def test_a_session_that_ended_sends_the_start_page_to_the_sign_in_page_when_a_table_is_opened(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], Any],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    person = record_page_errors(open_person(**DESKTOP), page_errors, console=False)
    # The page asks for the account when it opens; a session that ends before that answer reloads the page by itself.
    with person.expect_response(f"**{ACCOUNT_PATH}"):
        person.goto(f"{e2e_server.base_url}/")
    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible()
    e2e_server.stores.sessions.delete(member_of(person).session.id)
    before = table_count(e2e_server)

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    person.get_by_role("button", name=OPEN_TABLE).click()

    expect(person).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    assert table_count(e2e_server) == before


def test_a_visitor_without_a_session_gets_the_sign_in_page_for_a_link_and_no_table_data(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    visitor = record_page_errors(open_person(signed_in=False), page_errors)
    before = table_count(e2e_server)

    visitor.goto(f"{e2e_server.base_url}{path}")

    expect(visitor).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    expect(visitor.get_by_text(catalog_text("waitingForPlayers"))).to_have_count(0)
    answer = visitor.request.post(
        f"{e2e_server.base_url}{TABLES_PATH}",
        data={"command_id": "command-0001", "series_length": SERIES_LENGTH_DEFAULT},
        headers=same_origin(e2e_server),
    )
    assert answer.status == UNAUTHORIZED
    assert table_count(e2e_server) == before


def test_a_signed_in_person_the_group_does_not_admit_gets_no_table_and_writes_none(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    outsider = record_page_errors(open_person(signed_in=False, **DESKTOP), page_errors)
    sign_in_at_issuer(outsider, e2e_server, username="ben", groups=["/apps/other"])
    outsider.goto(f"{e2e_server.base_url}{LOGIN_PATH}")
    outsider.get_by_role("link", name="Log in", exact=True).click()
    before = table_count(e2e_server)

    outsider.goto(f"{e2e_server.base_url}{path}")

    expect(outsider.get_by_text(catalog_text("waitingForPlayers"))).to_have_count(0)
    assert outsider.request.get(f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(path)}").status == UNAUTHORIZED
    events = f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}"
    assert outsider.request.get(events).status == UNAUTHORIZED
    answer = outsider.request.post(
        f"{e2e_server.base_url}{TABLES_PATH}",
        data={"command_id": "command-0001", "series_length": SERIES_LENGTH_DEFAULT},
        headers=same_origin(e2e_server),
    )
    assert answer.status == UNAUTHORIZED
    assert table_count(e2e_server) == before
