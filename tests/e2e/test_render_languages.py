"""Skat in each further language: no key, function or object shows as text, `<html lang>` names the language and no
text runs over its box, at the phone and the desktop width."""

import re
from typing import TYPE_CHECKING, Any, get_args
from urllib.parse import quote

import pytest
from design.words import text as kit_text
from playwright.sync_api import Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.constants import (
    AUTH_CALLBACK_PATH,
    AUTH_START_PATH,
    CALL_SIGN_IN_PATH,
    LOGIN_PATH,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
)
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import LANGUAGES, SOURCE_LANGUAGE, Key, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.declaring import DEFAULT_JOINERS, DEFAULT_OPENER, DeclaringTable
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.kontra import KONTRA_OPTIONS, say_kontra_as_an_opponent
from tests.e2e.support.people import FORM_FACTORS, PERSON_ADDRESS_BASE, person_address_offsets, playwright_cookie
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_new_table, open_table_with_options, sit_in, table_id_of, watch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import Browser, BrowserContext

    from skat.web.words import Language
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

FURTHER_LANGUAGES: list[Language] = [language for language in LANGUAGES if language != SOURCE_LANGUAGE]
FORGED_CALLBACK = f"{AUTH_CALLBACK_PATH}?state=forged&code=x"
ROUTE_THAT_DOES_NOT_EXIST = "/no-such-page"
CATALOG_KEYS: tuple[str, ...] = get_args(Key.__value__)
# The first line of a function's source and the text of an object that was never turned into words.
SOURCE_OF_A_FUNCTION = re.compile(r"=>|\bfunction\b\s*\(")
FINDINGS_OF_A_RENDER = """(keys) => {
    const shown = document.body.innerText;
    const findings = keys.filter((key) => shown.includes(key)).map((key) => `key ${key}`);
    if (shown.includes("[object Object]")) findings.push("[object Object]");
    const overflowing = [...document.body.querySelectorAll("*")]
        .filter((element) => [...element.childNodes].some((node) => node.nodeType === 3 && node.textContent.trim()))
        .filter((element) => !["auto", "scroll"].includes(getComputedStyle(element).overflowX))
        // An ellipsis is a name the box shortens on purpose, as the lobby does for the tables other people left open.
        .filter((element) => getComputedStyle(element).textOverflow !== "ellipsis")
        // A one pixel box is a label only a screen reader reads.
        .filter((element) => element.clientWidth > 1 && element.scrollWidth > element.clientWidth)
        .map((element) => `${element.tagName.toLowerCase()}.${element.className} ${element.textContent.trim()}`);
    return { shown, findings, overflowing };
}"""


def assert_renders_in(person: Page, language: Language) -> None:
    assert person.locator("html").get_attribute("lang") == language
    outcome = person.evaluate(FINDINGS_OF_A_RENDER, list(CATALOG_KEYS))
    assert outcome["findings"] == []
    assert SOURCE_OF_A_FUNCTION.search(outcome["shown"]) is None
    assert outcome["overflowing"] == []


@pytest.fixture
def open_in_language(
    browser: Browser,
    browser_context_args: dict[str, Any],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> Iterator[Callable[..., Page]]:
    """A page of a person who already sits at a table, in a language: the same account in a context of its own."""
    contexts: list[BrowserContext] = []

    def open_page(member: SeededMember, language: Language, form_factor: dict[str, Any]) -> Page:
        address = str(PERSON_ADDRESS_BASE + next(person_address_offsets))
        context = browser.new_context(
            **{
                **browser_context_args,
                "locale": language,
                "extra_http_headers": {"X-Forwarded-For": address},
                **form_factor,
            }
        )
        contexts.append(context)
        context.add_cookies(
            [playwright_cookie(header, e2e_server.config, e2e_server.host) for header in member.set_cookie_headers]
        )
        return record_page_errors(context.new_page(), page_errors)

    yield open_page
    for context in contexts:
        context.close()


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(
    ("path", "status", "action_key"),
    [
        pytest.param(LOGIN_PATH, 200, "signIn.logIn", id="signed-out"),
        pytest.param(CALL_SIGN_IN_PATH, 200, "signIn.logIn", id="call"),
        pytest.param(FORGED_CALLBACK, 403, "signIn.tryAgain", id="login-failed"),
        pytest.param(NO_ACCESS_PATH, 200, "signIn.logOut", id="no-access"),
    ],
)
def test_each_sign_in_page_reads_in_the_language_the_browser_asks_for(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
    path: str,
    status: int,
    action_key: str,
) -> None:
    person = record_page_errors(
        open_person(signed_in=False, locale=language, **form_factor), page_errors, console=status == 200
    )

    response = person.goto(f"{e2e_server.base_url}{path}")

    assert response is not None
    assert response.status == status
    expect(person).to_have_title(text(language, "app.name"))
    action = kit_text(language, action_key)
    expect(
        person.get_by_role("link", name=action, exact=True).or_(person.get_by_role("button", name=action, exact=True))
    ).to_have_count(1)
    for key in ("legal.imprint", "legal.privacy", "legal.terms"):
        expect(person.get_by_role("link", name=text(language, key))).to_have_count(1)
    assert_renders_in(person, language)


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_call_sign_in_page_hydrates_in_the_language_the_browser_asks_for(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
) -> None:
    table_path = f"{TABLE_PAGE_PREFIX}{'0' * 32}"
    person = record_page_errors(open_person(signed_in=False, locale=language, **form_factor), page_errors)

    person.goto(f"{e2e_server.base_url}{CALL_SIGN_IN_PATH}?{RETURN_PATH_QUERY_NAME}={quote(table_path, safe='')}")

    # Only the page's script knows the table, so its sign-in address carries the return path once it has hydrated.
    expect(person.get_by_role("link", name=kit_text(language, "signIn.logIn"), exact=True)).to_have_attribute(
        "href", f"{AUTH_START_PATH}?{RETURN_PATH_QUERY_NAME}={quote(table_path, safe='')}"
    )
    assert_renders_in(person, language)


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_start_page_reads_in_the_language_the_browser_asks_for(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
) -> None:
    person = record_page_errors(open_person(locale=language, **form_factor), page_errors)

    person.goto(f"{e2e_server.base_url}/")

    expect(person.get_by_role("button", name=text(language, "start.newTable"))).to_be_visible()
    assert_renders_in(person, language)


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_the_error_page_reads_in_the_language_the_browser_asks_for(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
) -> None:
    person = record_page_errors(open_person(locale=language, **form_factor), page_errors, console=False)
    person.route(
        f"{e2e_server.base_url}{ROUTE_THAT_DOES_NOT_EXIST}",
        lambda route: route.fulfill(response=route.fetch(url=f"{e2e_server.base_url}/")),
    )

    person.goto(f"{e2e_server.base_url}{ROUTE_THAT_DOES_NOT_EXIST}")

    expect(person.get_by_text(text(language, "app.pageNotFound"))).to_be_visible()
    assert_renders_in(person, language)


class KontraTable(DeclaringTable):
    """A table opened through the API with Kontra and Re."""

    @staticmethod
    def _open_table(
        opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember], *, running_points: bool
    ) -> str:
        assert not running_points
        return open_table_with_options(
            opener, server, RawSession(server, member_of(opener)), {"kontra": KONTRA_OPTIONS}
        )


def read_the_table_in(
    open_in_language: Callable[..., Page],
    server: RunningServer,
    member: SeededMember,
    language: Language,
    form_factor: dict[str, Any],
    table_id: str,
) -> Page:
    reader = open_in_language(member, language, form_factor)
    reader.goto(f"{server.base_url}{TABLE_PAGE_PREFIX}{table_id}")
    expect(reader.locator(".chair")).to_have_count(3)
    return reader


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_table_reads_in_the_language_while_bidding(
    open_person: Callable[..., Page],
    open_in_language: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
) -> None:
    opener = record_page_errors(open_person(username=DEFAULT_OPENER, **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    for seat, username in zip((2, 3), DEFAULT_JOINERS, strict=True):
        joiner = record_page_errors(open_person(username=username, **form_factor), page_errors)
        watch(joiner, e2e_server, path)
        sit_in(joiner, seat)

    reader = read_the_table_in(
        open_in_language, e2e_server, member_of(opener), language, form_factor, table_id_of(path)
    )

    expect(reader.get_by_text(text(language, "table.bidding"))).to_be_visible()
    assert_renders_in(reader, language)


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_table_reads_in_the_language_while_the_declarer_declares(
    open_person: Callable[..., Page],
    open_in_language: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
) -> None:
    table = DeclaringTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.declare_through_the_api(action="take")

    reader = read_the_table_in(
        open_in_language, e2e_server, member_of(table.declarer), language, form_factor, table.table_id
    )

    expect(reader.get_by_role("button", name=text(language, "declare.putBack"))).to_be_visible()
    assert_renders_in(reader, language)


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_table_reads_in_the_language_in_play_with_a_kontra_said(
    open_person: Callable[..., Page],
    open_in_language: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=KontraTable)
    say_kontra_as_an_opponent(table)
    seat = table.seat_at["middlehand"]

    reader = read_the_table_in(
        open_in_language,
        e2e_server,
        member_of(table.pages[seat]),
        language,
        form_factor,
        table.declaring.table_id,
    )

    expect(reader.get_by_text(text(language, "kontra.kontra"), exact=False).first).to_be_visible()
    assert_renders_in(reader, language)


def played_out_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> PlayingTable:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
    table.play_out(CARDS_IN_A_GAME)
    return table


@pytest.mark.parametrize("language", FURTHER_LANGUAGES)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize("waiting", [False, True], ids=["result", "weiter-bar-waiting"])
def test_a_table_reads_in_the_language_on_a_result_and_with_the_weiter_bar_waiting(
    open_person: Callable[..., Page],
    open_in_language: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    language: Language,
    waiting: bool,
) -> None:
    table = played_out_table(open_person, e2e_server, member_of, page_errors, form_factor)
    seat = table.seat_at["forehand"]
    if waiting:
        table.ready_through_the_api(seat)

    reader = read_the_table_in(
        open_in_language,
        e2e_server,
        member_of(table.pages[seat]),
        language,
        form_factor,
        table.declaring.table_id,
    )

    expect(reader.locator(".result")).to_be_visible()
    if waiting:
        expect(reader.get_by_text(text(language, "table.waitingFor", names="").strip()).first).to_be_visible()
    assert_renders_in(reader, language)
