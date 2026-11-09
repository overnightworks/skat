import re
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import pytest
from playwright.sync_api import FrameLocator, Locator, Page, expect

from skat.web.constants import AUTH_START_PATH, CALL_SIGN_IN_PATH, LOGIN_PATH, RETURN_PATH_QUERY_NAME
from tests.e2e.support.browser import record_page_errors, sign_in_at_issuer
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
from tests.e2e.support.people import FORM_FACTORS, SMALL_PHONE, WIDTHS, playwright_cookie
from tests.support.sign_in_settings import TEST_ISSUER
from tests.support.signed_in import seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

# The words are appkit's English: the sign-in pages keep them.
LOG_IN = "Log in"
UNFINISHED_NOTICE = "Sign-in did not finish."
SIGNING_IN = "Signing in"
OPEN_IN_TAB = "Open in a tab"
NO_ACCESS = "No access"
LOG_OUT = "Log out"
NOT_ADMITTED = ["/apps/other"]
# The window and the frame meet within a poll or two; a bound stops a hang.
WAIT_MILLISECONDS = 10_000
FRAMED_STYLE = "position:fixed;inset:0;width:100%;height:100%;border:0"
# The sandboxed frame that cannot open a window.
WINDOW_BLOCKED = "window.open = () => null;"
FITS_ITS_WIDTH = "page => page.scrollWidth <= page.clientWidth"


@dataclass(frozen=True)
class FramedTable:
    visitor: Page
    path: str
    session_cookie: str

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

        def frame(*, init_script: str | None = None, **device_options: Any) -> FramedTable:
            path = new_table(open_person, signing_server)
            visitor = record_page_errors(
                open_person(signed_in=False, server=signing_server, **device_options),
                page_errors,
                signed_out_account_check_origin=signing_server.base_url,
            )
            if init_script is not None:
                visitor.add_init_script(init_script)
            body = page_holding(table_url(signing_server, path), FRAMED_STYLE)
            stack.enter_context(served_from(CALL_ORIGIN, visitor, browser_coverage, body))
            visitor.goto(f"{CALL_ORIGIN}/")
            framed = FramedTable(visitor, path, signing_server.config.session_cookie_name)
            # The link carries the return address only once the page's script has run, so a tap before it is no window.
            expect(framed.log_in).to_have_attribute("href", re.compile(re.escape(RETURN_PATH_QUERY_NAME)))
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
    expect(framed.frame.get_by_role("heading", name=SIGNING_IN)).to_be_visible()

    with framed.visitor.expect_popup() as opened:
        framed.frame.get_by_role("link", name=OPEN_IN_TAB).click()
    tab = opened.value
    expect(tab).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    tab.get_by_role("link", name=LOG_IN, exact=True).click()

    expect(framed.frame.locator(CHAIR)).to_have_count(THREE_CHAIRS, timeout=WAIT_MILLISECONDS)
    assert framed.frame_address == table_url(signing_server, framed.path)


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
