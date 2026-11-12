import re
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from playwright.sync_api import FrameLocator, Locator, Page, Route, expect

from skat.web.constants import (
    ACCOUNT_PATH,
    APP_ASSET_PATH,
    AUTH_START_PATH,
    CALL_MODE,
    CALL_SIGN_IN_PATH,
    IMMUTABLE_ASSET_DIRECTORY,
    LOGIN_PATH,
    MODE_QUERY_NAME,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
)
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import LEGAL_LINKS, LEGAL_ORIGIN, record_page_errors, sign_in_at_issuer
from tests.e2e.support.call_frame import (
    CALL_ORIGIN,
    CALL_PORT,
    CHAIR,
    FRAME,
    FRAME_REFUSED,
    OTHER_HOST,
    THREE_CHAIRS,
    new_table,
    page_holding,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.kit_words import kit_text
from tests.e2e.support.people import DESKTOP, FORM_FACTORS, PHONE, SMALL_PHONE, WIDTHS, playwright_cookie
from tests.e2e.support.sessions import end_sessions_of
from tests.e2e.support.tables import open_new_table
from tests.support.sign_in_settings import TEST_ISSUER
from tests.support.signed_in import seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

# The words are design's English: the sign-in pages keep them.
LOG_IN = kit_text("signIn.logIn")
UNFINISHED_NOTICE = kit_text("signIn.signInUnfinished")
SIGNING_IN = kit_text("signIn.signingIn")
BLOCKED = kit_text("signIn.windowBlocked")
BLOCKED_SENTENCE = kit_text("signIn.windowBlockedSentence")
OPEN_IN_TAB = kit_text("signIn.openInTab")
NO_ACCESS = kit_text("signIn.noAccess")
LOG_OUT = kit_text("signIn.logOut")
NOT_ADMITTED = ["/apps/other"]
# The window and the frame meet within a poll or two; a bound stops a hang.
WAIT_MILLISECONDS = 10_000
STALE_STAGE = ".stage.stale"
FRAMED_STYLE = "position:fixed;inset:0;width:100%;height:100%;border:0"
# The sandboxed frame that cannot open a window.
WINDOW_BLOCKED = "window.open = () => null;"
FITS_ITS_WIDTH = "page => page.scrollWidth <= page.clientWidth"
# The build's module files, which a test withholds so that a page loads without its script.
MODULE_FILES = f"**{APP_ASSET_PATH}/{IMMUTABLE_ASSET_DIRECTORY}/**"
MODULE_FETCH_FAILED = "Failed to fetch dynamically imported module: "
# Virtual time well past any interval at which the page asks again whether the person signed in.
LONGER_THAN_ANY_RE_CHECK_MILLISECONDS = 60_000
# The legal origin refuses to be framed, as hallucinai.de does.
NOT_FRAMEABLE = {"content-security-policy": "frame-ancestors 'none'"}


@dataclass(frozen=True)
class FramedTable:
    visitor: Page
    path: str
    session_cookie: str
    requests: list[str]
    release_script: Callable[[], None]

    @property
    def sign_in_starts(self) -> list[str]:
        return [url for url in self.requests if AUTH_START_PATH in url]

    @property
    def frame(self) -> FrameLocator:
        return self.visitor.frame_locator(FRAME)

    @property
    def log_in(self) -> Locator:
        return self.frame.get_by_role("link", name=LOG_IN, exact=True)

    @property
    def frame_address(self) -> str:
        return self.visitor.frames[1].url

    def has_session(self) -> bool:
        return any(cookie["name"] == self.session_cookie for cookie in self.visitor.context.cookies())


def abort_request(route: Route) -> None:
    route.abort()


def wait_for_script(framed: FramedTable) -> None:
    """The link carries the return address only once the page's script has run, so a tap before it is no window."""
    expect(framed.log_in).to_have_attribute("href", re.compile(re.escape(RETURN_PATH_QUERY_NAME)))


@pytest.fixture(scope="module")
def signing_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("signing"), call_origin=CALL_ORIGIN)


@pytest.fixture
def frame_a_table(
    open_person: Callable[..., Page],
    signing_server: RunningServer,
    browser_coverage: BrowserCoverage,
    page_errors: list[str],
    expected_request_failures: list[str],
) -> Iterator[Callable[..., FramedTable]]:
    """Opens a table, then a signed-out person's call page that frames it."""
    expected_request_failures.append(TEST_ISSUER)
    with ExitStack() as stack:

        def frame(
            *,
            init_script: str | None = None,
            username: str | None = None,
            console: bool = True,
            script_withheld: bool = False,
            clock: bool = False,
            **device_options: Any,
        ) -> FramedTable:
            """A signed-out person, or `username` signed in; `script_withheld` loads no page script,
            `clock` lets a test run virtual time."""
            path = new_table(open_person, signing_server)
            visitor = record_page_errors(
                open_person(signed_in=username is not None, username=username, server=signing_server, **device_options),
                page_errors,
                console=console,
                signed_out_account_check_origin=signing_server.base_url,
            )
            requests: list[str] = []
            visitor.on("request", lambda request: requests.append(request.url))
            if init_script is not None:
                visitor.add_init_script(init_script)
            body = page_holding(table_url(signing_server, path), FRAMED_STYLE)
            stack.enter_context(served_from(CALL_ORIGIN, visitor, browser_coverage, body))
            if clock:
                visitor.clock.install()
            if script_withheld:
                expected_request_failures.append(
                    f"{signing_server.base_url}{APP_ASSET_PATH}/{IMMUTABLE_ASSET_DIRECTORY}/"
                )
                visitor.context.route(MODULE_FILES, abort_request)
            visitor.goto(f"{CALL_ORIGIN}/")
            framed = FramedTable(
                visitor,
                path,
                signing_server.config.session_cookie_name,
                requests,
                lambda: visitor.context.unroute(MODULE_FILES, abort_request),
            )
            if username is not None:
                expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS)
            elif not script_withheld:
                wait_for_script(framed)
            return framed

        yield frame


def start_sign_in(framed: FramedTable) -> Page:
    with framed.visitor.expect_popup() as opened:
        framed.log_in.click()
    return opened.value


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_signed_out_frame_signs_in_in_a_separate_window_that_closes_and_the_frame_shows_the_table(
    frame_a_table: Callable[..., FramedTable], signing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    framed = frame_a_table(**form_factor)
    sign_in_at_issuer(framed.visitor, signing_server, username="anna")
    expect(framed.log_in).to_be_visible()
    expect(framed.frame.locator(CHAIR)).to_have_count(0)

    window = start_sign_in(framed)

    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()
    expect(framed.frame.get_by_role("link", name=OPEN_IN_TAB)).to_have_attribute("href", framed.path)
    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)
    assert window.is_closed()
    assert framed.frame_address == table_url(signing_server, framed.path)
    assert framed.has_session()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_window_closed_before_the_sign_in_finishes_leaves_the_sign_in_face_with_its_notice(
    frame_a_table: Callable[..., FramedTable], form_factor: dict[str, Any]
) -> None:
    framed = frame_a_table(**form_factor)
    start_sign_in(framed).close()

    expect(framed.frame.get_by_text(UNFINISHED_NOTICE)).to_be_visible(timeout=WAIT_MILLISECONDS)
    expect(framed.log_in).to_be_visible()
    assert not framed.has_session()
    assert len(framed.visitor.context.pages) == 1

    second = start_sign_in(framed)

    assert not second.is_closed()
    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()


def test_a_window_on_the_issuers_origin_keeps_the_sign_in_face_until_it_is_closed(
    frame_a_table: Callable[..., FramedTable],
) -> None:
    framed = frame_a_table(clock=True)
    framed.visitor.context.route(
        f"**{AUTH_START_PATH}**",
        lambda route: route.fulfill(
            content_type="text/html", body=f"<script>location.replace('{TEST_ISSUER}/auth')</script>"
        ),
    )
    framed.visitor.context.route(
        f"{TEST_ISSUER}/**", lambda route: route.fulfill(content_type="text/html", body="<p>issuer</p>")
    )
    window = start_sign_in(framed)
    window.wait_for_url(re.compile(re.escape(TEST_ISSUER)))

    framed.visitor.clock.run_for(LONGER_THAN_ANY_RE_CHECK_MILLISECONDS)

    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()
    assert not window.is_closed()
    window.close()
    framed.visitor.clock.run_for(LONGER_THAN_ANY_RE_CHECK_MILLISECONDS)
    expect(framed.frame.get_by_text(UNFINISHED_NOTICE)).to_be_visible(timeout=WAIT_MILLISECONDS)


def test_a_window_closed_while_the_account_check_fails_leaves_the_sign_in_face_with_its_notice(
    frame_a_table: Callable[..., FramedTable], signing_server: RunningServer, expected_request_failures: list[str]
) -> None:
    framed = frame_a_table(clock=True, console=False)
    expected_request_failures.append(f"{signing_server.base_url}{ACCOUNT_PATH}")
    framed.visitor.context.route(f"**{ACCOUNT_PATH}", abort_request)
    window = start_sign_in(framed)

    window.close()
    framed.visitor.clock.run_for(LONGER_THAN_ANY_RE_CHECK_MILLISECONDS)

    expect(framed.frame.get_by_text(UNFINISHED_NOTICE)).to_be_visible(timeout=WAIT_MILLISECONDS)


def test_a_sign_in_finished_in_another_window_brings_the_table_when_the_sign_in_window_is_closed(
    frame_a_table: Callable[..., FramedTable], signing_server: RunningServer
) -> None:
    framed = frame_a_table()
    window = start_sign_in(framed)
    member = seed_member(signing_server.stores, signing_server.config)
    framed.visitor.context.add_cookies(
        [playwright_cookie(header, signing_server.config, signing_server.host) for header in member.set_cookie_headers]
    )

    window.close()

    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_account_outside_the_group_sees_no_access_without_a_log_out_and_the_call_goes_on(
    frame_a_table: Callable[..., FramedTable], signing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    framed = frame_a_table(**form_factor)
    sign_in_at_issuer(framed.visitor, signing_server, username="ben", groups=NOT_ADMITTED)

    window = start_sign_in(framed)

    expect(framed.frame.get_by_role("heading", name=NO_ACCESS)).to_be_visible(timeout=WAIT_MILLISECONDS)
    expect(framed.frame.get_by_role("button", name=LOG_OUT)).to_have_count(0)
    assert framed.frame.locator("html").evaluate(FITS_ITS_WIDTH)
    assert window.is_closed()
    assert not framed.has_session()
    assert framed.visitor.evaluate("() => document.title") == "call"


def test_the_faces_fit_the_frame_of_the_smallest_phone(frame_a_table: Callable[..., FramedTable]) -> None:
    framed = frame_a_table(**SMALL_PHONE)
    expect(framed.log_in).to_be_visible()
    assert framed.frame.locator("html").evaluate(FITS_ITS_WIDTH)

    start_sign_in(framed)

    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()
    assert framed.frame.locator("html").evaluate(FITS_ITS_WIDTH)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_blocked_window_leaves_a_plain_link_whose_tab_signs_in_and_brings_the_table(
    frame_a_table: Callable[..., FramedTable], signing_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    framed = frame_a_table(init_script=WINDOW_BLOCKED, **form_factor)
    sign_in_at_issuer(framed.visitor, signing_server, username="cora")
    framed.log_in.click()
    expect(framed.frame.get_by_role("heading", name=BLOCKED)).to_be_visible()

    with framed.visitor.expect_popup() as opened:
        framed.frame.get_by_role("link", name=OPEN_IN_TAB).click()
    tab = opened.value
    expect(tab).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    tab.get_by_role("link", name=LOG_IN, exact=True).click()

    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)
    assert framed.frame_address == table_url(signing_server, framed.path)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_blocked_window_shows_the_blocked_face_with_the_tab_link_and_focuses_its_heading(
    frame_a_table: Callable[..., FramedTable], form_factor: dict[str, Any]
) -> None:
    framed = frame_a_table(init_script=WINDOW_BLOCKED, **form_factor)

    framed.log_in.click()

    heading = framed.frame.get_by_role("heading", name=BLOCKED)
    expect(heading).to_be_focused()
    expect(framed.frame.get_by_text(BLOCKED_SENTENCE)).to_be_visible()
    expect(framed.frame.get_by_role("link", name=OPEN_IN_TAB)).to_have_attribute("href", framed.path)
    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_have_count(0)


def test_a_return_address_that_is_no_table_leaves_the_plain_start_link_and_opens_no_window(
    open_person: Callable[..., Page],
    signing_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(TEST_ISSUER)
    person = record_page_errors(open_person(signed_in=False, server=signing_server), page_errors)
    windows: list[Page] = []
    person.on("popup", lambda window: windows.append(window))
    foreign = f"//{OTHER_HOST}/anything"

    person.goto(f"{signing_server.base_url}{CALL_SIGN_IN_PATH}?{RETURN_PATH_QUERY_NAME}={quote(foreign, safe='')}")
    link = person.get_by_role("link", name=LOG_IN, exact=True)

    expect(link).to_have_attribute("href", AUTH_START_PATH)
    with person.expect_event("requestfailed"):
        link.click()
    assert windows == []


def test_a_frame_of_another_origin_shows_no_sign_in_face(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    signing_server: RunningServer,
    expected_request_failures: list[str],
) -> None:
    path = new_table(open_person, signing_server)
    expected_request_failures.extend([table_url(signing_server, path), f"{signing_server.base_url}{CALL_SIGN_IN_PATH}"])
    other_origin = f"https://{OTHER_HOST}:{CALL_PORT}"
    visitor = open_person(signed_in=False, server=signing_server)

    with (
        served_from(other_origin, visitor, browser_coverage, page_holding(table_url(signing_server, path))),
        visitor.expect_console_message(lambda message: FRAME_REFUSED in message.text),
    ):
        visitor.goto(f"{other_origin}/")

    expect(visitor.locator(FRAME)).to_be_attached()
    expect(visitor.frame_locator(FRAME).get_by_role("link", name=LOG_IN)).to_have_count(0)


@pytest.mark.parametrize("link_name", LEGAL_LINKS)
@pytest.mark.parametrize(
    ("form_factor", "framed"),
    [
        pytest.param(PHONE, True, id="framed-390"),
        pytest.param(DESKTOP, True, id="framed-1280"),
        pytest.param(DESKTOP, False, id="top-level"),
    ],
)
def test_a_legal_link_of_the_table_opens_the_central_page_in_a_new_tab_and_the_table_stays(
    open_person: Callable[..., Page],
    signing_server: RunningServer,
    browser_coverage: BrowserCoverage,
    link_name: str,
    form_factor: dict[str, Any],
    framed: bool,
) -> None:
    path = new_table(open_person, signing_server)
    visitor = open_person(server=signing_server, **form_factor)
    visitor.context.route(
        f"{LEGAL_ORIGIN}/**", lambda route: route.fulfill(status=200, content_type="text/html", body="legal")
    )
    with ExitStack() as stack:
        if framed:
            body = page_holding(table_url(signing_server, path), FRAMED_STYLE)
            stack.enter_context(served_from(CALL_ORIGIN, visitor, browser_coverage, body))
            visitor.goto(f"{CALL_ORIGIN}/")
            table: Page | FrameLocator = visitor.frame_locator(FRAME)
        else:
            visitor.goto(f"{signing_server.base_url}{path}")
            table = visitor
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)

        with visitor.context.expect_page() as opened:
            table.get_by_role("link", name=text(SOURCE_LANGUAGE, link_name), exact=True).click()

        assert opened.value.url == LEGAL_LINKS[link_name]
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        if framed:
            assert visitor.frames[1].url == table_url(signing_server, path)


def lose_the_session(
    framed: FramedTable, open_person: Callable[..., Page], server: RunningServer, username: str
) -> None:
    """Skat ends the person's session; another person's change at the table is the disclosure it no longer gets."""
    end_sessions_of(server, username)
    changer = open_person(server=server)
    changer.goto(f"{server.base_url}{framed.path}")


def expect_the_call_sign_in_face(framed: FramedTable) -> None:
    """The reload led the frame to the call sign-in page with the call-mode table as its return address."""
    expect(framed.log_in).to_be_visible(timeout=WAIT_MILLISECONDS)
    address = urlsplit(framed.frame_address)
    assert address.path == CALL_SIGN_IN_PATH
    assert parse_qs(address.query) == {RETURN_PATH_QUERY_NAME: [f"{framed.path}?{MODE_QUERY_NAME}={CALL_MODE}"]}
    wait_for_script(framed)
    assert framed.sign_in_starts == []


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_framed_table_whose_session_ended_shows_the_sign_in_face_and_one_tap_brings_the_table_back(
    frame_a_table: Callable[..., FramedTable],
    open_person: Callable[..., Page],
    signing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    framed = frame_a_table(username="gina", console=False, **form_factor)
    sign_in_at_issuer(framed.visitor, signing_server, username="gina")

    lose_the_session(framed, open_person, signing_server, "gina")

    expect_the_call_sign_in_face(framed)
    expect(framed.frame.locator(CHAIR)).to_have_count(0)
    window = start_sign_in(framed)
    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)
    assert window.is_closed()
    assert framed.frame_address == table_url(signing_server, framed.path)
    assert framed.has_session()
    assert framed.sign_in_starts == []


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_framed_table_whose_issuer_session_ended_too_signs_in_again_in_the_window_on_the_second_tap(
    frame_a_table: Callable[..., FramedTable],
    open_person: Callable[..., Page],
    signing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    framed = frame_a_table(username="hugo", console=False, **form_factor)
    lose_the_session(framed, open_person, signing_server, "hugo")
    expect_the_call_sign_in_face(framed)

    window = start_sign_in(framed)
    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()
    expect(framed.frame.get_by_role("link", name=OPEN_IN_TAB)).to_have_attribute("href", framed.path)
    window.close()

    expect(framed.frame.get_by_text(UNFINISHED_NOTICE)).to_be_visible(timeout=WAIT_MILLISECONDS)
    assert signing_server.stores.sessions.records_of("subject-hugo").sessions == ()
    sign_in_at_issuer(framed.visitor, signing_server, username="hugo")
    start_sign_in(framed)

    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)
    assert framed.frame_address == table_url(signing_server, framed.path)
    assert framed.sign_in_starts == []


def test_the_face_of_a_framed_table_whose_session_ended_fits_the_frame_of_the_smallest_phone(
    frame_a_table: Callable[..., FramedTable], open_person: Callable[..., Page], signing_server: RunningServer
) -> None:
    framed = frame_a_table(username="ines", console=False, **SMALL_PHONE)

    lose_the_session(framed, open_person, signing_server, "ines")

    expect_the_call_sign_in_face(framed)
    assert framed.frame.locator("html").evaluate(FITS_ITS_WIDTH)


@pytest.mark.parametrize("link_name", LEGAL_LINKS)
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_legal_link_of_the_framed_sign_in_face_opens_in_a_new_tab_and_starts_no_account_check(
    frame_a_table: Callable[..., FramedTable], link_name: str, form_factor: dict[str, Any]
) -> None:
    framed = frame_a_table(clock=True, **form_factor)
    framed.visitor.context.route(
        f"{LEGAL_ORIGIN}/**",
        lambda route: route.fulfill(status=200, content_type="text/html", headers=NOT_FRAMEABLE, body="legal"),
    )
    face_address = framed.frame_address
    framed.requests.clear()

    with framed.visitor.context.expect_page() as opened:
        framed.frame.get_by_role("link", name=text(SOURCE_LANGUAGE, link_name), exact=True).click()

    assert opened.value.url == LEGAL_LINKS[link_name]
    assert framed.frame_address == face_address
    expect(framed.log_in).to_be_visible()
    framed.visitor.clock.run_for(LONGER_THAN_ANY_RE_CHECK_MILLISECONDS)
    assert not any(ACCOUNT_PATH in url for url in framed.requests)
    assert not any(url.startswith(LEGAL_ORIGIN) for url in framed.requests)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_tap_on_log_in_before_the_script_has_run_reloads_the_face_and_a_legal_link_stays_out_of_the_frame(
    frame_a_table: Callable[..., FramedTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    framed = frame_a_table(script_withheld=True, console=False, **form_factor)
    framed.visitor.context.route(
        f"{LEGAL_ORIGIN}/**",
        lambda route: route.fulfill(status=200, content_type="text/html", headers=NOT_FRAMEABLE, body="legal"),
    )
    expect(framed.log_in).to_be_visible()
    face_address = framed.frame_address
    assert RETURN_PATH_QUERY_NAME in face_address

    with framed.visitor.context.expect_page() as opened:
        framed.frame.get_by_role("link", name=text(SOURCE_LANGUAGE, "legal.privacy"), exact=True).click()
    assert opened.value.url == LEGAL_LINKS["legal.privacy"]
    assert framed.frame_address == face_address

    with framed.visitor.expect_event("framenavigated", lambda frame: frame.parent_frame is not None):
        framed.log_in.click()
    assert framed.frame_address == face_address
    expect(framed.log_in).to_be_visible()

    framed.release_script()
    with framed.visitor.expect_event("framenavigated", lambda frame: frame.parent_frame is not None):
        framed.log_in.click()
    wait_for_script(framed)
    assert framed.frame_address == face_address

    start_sign_in(framed)

    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()
    assert framed.sign_in_starts == []
    assert not any(url.startswith(LEGAL_ORIGIN) for url in framed.requests)
    # The only script errors are the withheld module files that the test named.
    page_errors[:] = [error for error in page_errors if not error.startswith(MODULE_FETCH_FAILED)]


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_top_level_call_mode_table_whose_session_ended_signs_in_again_through_the_issuer_without_a_click(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    path = open_new_table(open_person(username="jana", **form_factor), e2e_server)
    ben = record_page_errors(open_person(username="ben", **form_factor), page_errors, console=False)
    sign_in_at_issuer(ben, e2e_server, username="ben")
    sign_in_starts: list[str] = []
    ben.on("request", lambda request: sign_in_starts.append(request.url) if AUTH_START_PATH in request.url else None)
    ben.goto(table_url(e2e_server, path))
    expect(ben.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    ben.evaluate("window.sameDocument = true")
    end_sessions_of(e2e_server, "ben")

    open_person(**form_factor).goto(f"{e2e_server.base_url}{path}")

    ben.wait_for_function("() => window.sameDocument !== true")
    expect(ben).to_have_url(f"{e2e_server.base_url}{path}")
    expect(ben.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    assert [urlsplit(url).path for url in sign_in_starts] == [AUTH_START_PATH]
    return_path = f"{path}?{SIGNED_IN_AGAIN_QUERY_NAME}=1"
    assert parse_qs(urlsplit(sign_in_starts[0]).query) == {RETURN_PATH_QUERY_NAME: [return_path]}
    assert CALL_SIGN_IN_PATH not in ben.url


def test_a_framed_table_whose_stream_ends_without_a_refusal_dims_and_comes_back_without_reload_or_sign_in(
    frame_a_table: Callable[..., FramedTable], signing_server: RunningServer
) -> None:
    framed = frame_a_table(username="ines", console=False)
    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    streams: list[str] = []

    def end_the_first_stream(route: Route) -> None:
        streams.append(route.request.url)
        if len(streams) == 1:
            route.fulfill(content_type="text/event-stream", body="")
        else:
            route.continue_()

    # Playwright cannot end a stream that is open, so the reloaded frame meets a stream that answers and ends at once.
    framed.visitor.context.route(f"**{TABLES_PATH}/*{TABLE_EVENTS_SUFFIX}", end_the_first_stream)
    framed.visitor.frames[1].goto(table_url(signing_server, framed.path))
    framed.visitor.frames[1].evaluate("window.sameDocument = true")

    expect(framed.frame.locator(STALE_STAGE)).to_have_count(1, timeout=WAIT_MILLISECONDS)
    expect(framed.frame.locator(STALE_STAGE)).to_have_count(0, timeout=WAIT_MILLISECONDS)
    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    assert framed.visitor.frames[1].evaluate("window.sameDocument") is True
    assert framed.sign_in_starts == []
