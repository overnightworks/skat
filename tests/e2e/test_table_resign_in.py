import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

from skat.web.constants import AUTH_START_PATH, LOGIN_PATH, SIGNED_IN_AGAIN_QUERY_NAME
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors, sign_in_at_issuer
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.sessions import end_sessions_of
from tests.e2e.support.tables import open_new_table, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

WIDTHS = [pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
RECONNECTING = text(SOURCE_LANGUAGE, "table.reconnecting")
# The browser asks again a few seconds after a failed stream.
RECONNECT_TIMEOUT_MILLISECONDS = 15_000


def watching_signed_in_at_the_issuer(
    open_person: Callable[..., Page], server: RunningServer, path: str, page_errors: list[str], **form_factor: Any
) -> tuple[Page, list[str]]:
    """Ben signs in through the shared link and watches the table; the list fills with every sign-in start he makes."""
    # The 401 the page's session check meets is the console error, so only script errors are recorded.
    ben = record_page_errors(open_person(signed_in=False, **form_factor), page_errors, console=False)
    sign_in_at_issuer(ben, server, username="ben")
    sign_in_starts: list[str] = []
    ben.on("request", lambda request: sign_in_starts.append(request.url) if AUTH_START_PATH in request.url else None)
    ben.goto(f"{server.base_url}{path}")
    ben.get_by_role("link", name="Log in", exact=True).click()
    expect(ben).to_have_url(f"{server.base_url}{path}")
    expect(ben.locator(".chair")).to_have_count(3)
    sign_in_starts.clear()
    return ben, sign_in_starts


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_watching_member_whose_session_ended_is_back_at_the_table_through_the_sign_in_without_a_click(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    ben, sign_in_starts = watching_signed_in_at_the_issuer(open_person, e2e_server, path, page_errors, **form_factor)
    ben.evaluate("window.sameDocument = true")
    end_sessions_of(e2e_server, "ben")

    # A change at the table is the next disclosure, which the ended session no longer gets.
    cleo = record_page_errors(open_person(username="cleo", **form_factor), page_errors)
    cleo.goto(f"{e2e_server.base_url}{path}")

    # The marker is gone once the page has been to the sign-in and loaded again.
    ben.wait_for_function("() => window.sameDocument !== true")
    expect(ben.locator(".chair[data-seat='1'] .plate")).to_have_text("anna")
    expect(ben).to_have_url(f"{e2e_server.base_url}{path}")
    expect(ben.locator(".watchers span")).to_have_text("2")
    assert [urlsplit(url).path for url in sign_in_starts] == [AUTH_START_PATH]
    assert parse_qs(urlsplit(sign_in_starts[0]).query) == {"next": [f"{path}?{SIGNED_IN_AGAIN_QUERY_NAME}=1"]}


def test_a_second_refusal_soon_after_the_sign_in_shows_the_sign_in_page_instead_of_navigating_again(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    ben, sign_in_starts = watching_signed_in_at_the_issuer(open_person, e2e_server, path, page_errors, **DESKTOP)
    ben.evaluate("window.sameDocument = true")
    end_sessions_of(e2e_server, "ben")
    cleo = record_page_errors(open_person(username="cleo", **DESKTOP), page_errors)
    cleo.goto(f"{e2e_server.base_url}{path}")
    ben.wait_for_function("() => window.sameDocument !== true")
    expect(ben.locator(".chair[data-seat='1'] .plate")).to_have_text("anna")
    assert len(sign_in_starts) == 1
    ben.evaluate("window.sameDocument = true")

    end_sessions_of(e2e_server, "ben")
    cleo.close()

    expect(ben).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    expect(ben.get_by_role("link", name="Log in", exact=True)).to_be_visible()
    assert len(sign_in_starts) == 1


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_dropped_connection_dims_the_page_and_never_signs_in_again(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors, console=False)
    path = open_new_table(opener, e2e_server)
    sign_in_starts: list[str] = []
    opener.on("request", lambda request: sign_in_starts.append(request.url) if AUTH_START_PATH in request.url else None)
    # Chromium's offline mode does not cut an open EventSource, so the drop is an aborted route.
    events = f"**{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}"
    session_check = f"**{TABLES_PATH}/{table_id_of(path)}"
    opener.route(events, lambda route: route.abort())
    answered = []
    reloaded = []

    def answer_the_reloaded_page_load_then_drop(route: Route) -> None:
        # The page being replaced may still check its own session; only the reloaded page's first read is answered.
        if answered or not reloaded:
            route.abort()
            return
        answered.append(True)
        route.continue_()

    opener.route(session_check, answer_the_reloaded_page_load_then_drop)
    opener.once("framenavigated", lambda frame: reloaded.append(True))

    opener.reload()

    expect(opener.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    opener.unroute(events)
    opener.unroute(session_check)
    expect(opener.get_by_text(RECONNECTING)).to_be_hidden(timeout=RECONNECT_TIMEOUT_MILLISECONDS)
    assert sign_in_starts == []
