import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, expect

from skat.web.constants import AUTH_CALLBACK_PATH, AUTH_START_PATH, LOGIN_PATH, OIDC_CLIENT_ID
from tests.e2e.support.browser import ACCOUNT_AVATAR, record_page_errors, sign_in_at_issuer
from tests.e2e.support.people import FORM_FACTORS, playwright_cookie
from tests.e2e.support.server import LOOPBACK_HOST
from tests.support.sign_in_settings import TEST_ISSUER
from tests.support.signed_in import seed_member

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

START_PAGE_LINE = "Tische kommen als Nächstes."
SESSION_COOKIE = "__Host-session_id"


def open_documents(page: Page) -> list[str]:
    """The reader answers the document URLs the page requested so far."""
    requested: list[str] = []
    page.on(
        "request",
        lambda request: requested.append(request.url) if request.resource_type == "document" else None,
    )
    return requested


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_member_signs_in_at_the_issuer_and_reaches_the_start_page(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(signed_in=False, **form_factor), page_errors)
    sign_in_at_issuer(person, e2e_server, username="anna")

    person.goto(f"{e2e_server.base_url}{LOGIN_PATH}")
    person.get_by_role("link", name="Log in", exact=True).click()

    expect(person.get_by_text(START_PAGE_LINE)).to_be_visible()
    expect(person.locator(ACCOUNT_AVATAR)).to_be_visible()
    assert any(cookie["name"] == SESSION_COOKIE for cookie in person.context.cookies())


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_member_the_group_does_not_admit_sees_the_refusal_and_no_start_page(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(signed_in=False, **form_factor), page_errors)
    sign_in_at_issuer(person, e2e_server, username="ben", groups=["/apps/other"])

    person.goto(f"{e2e_server.base_url}{LOGIN_PATH}")
    person.get_by_role("link", name="Log in", exact=True).click()

    expect(person.get_by_role("button", name="Log out")).to_be_visible()
    expect(person.get_by_text(START_PAGE_LINE)).to_have_count(0)
    expect(person.locator(ACCOUNT_AVATAR)).to_have_count(0)
    assert not any(cookie["name"] == SESSION_COOKIE for cookie in person.context.cookies())


@pytest.mark.parametrize("path", ["/", "/anywhere", "/account"])
def test_a_visitor_without_a_session_sees_the_sign_in_page_and_its_link_leads_to_the_issuer_for_skats_client(
    open_person: Callable[..., Page],
    expected_request_failures: list[str],
    e2e_server: RunningServer,
    page_errors: list[str],
    path: str,
) -> None:
    expected_request_failures.append(TEST_ISSUER)
    person = record_page_errors(open_person(signed_in=False), page_errors)
    documents = open_documents(person)

    person.goto(f"{e2e_server.base_url}{path}")

    expect(person).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    with person.expect_event("requestfailed"):
        person.get_by_role("link", name="Log in", exact=True).click()
    start, issuer = documents[-2:]
    assert urlsplit(start).path == AUTH_START_PATH
    query = parse_qs(urlsplit(issuer).query)
    assert query["client_id"] == [OIDC_CLIENT_ID]
    assert query["redirect_uri"] == [f"{e2e_server.base_url}{AUTH_CALLBACK_PATH}"]


@pytest.mark.parametrize("session", ["forged", "expired"])
def test_a_forged_or_expired_session_cookie_is_treated_as_no_session(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    session: str,
) -> None:
    person = record_page_errors(open_person(signed_in=False), page_errors)
    if session == "expired":
        member = seed_member(e2e_server.stores, e2e_server.config, expires_in=timedelta(seconds=-60))
        cookies = [playwright_cookie(header, e2e_server.config) for header in member.set_cookie_headers]
    else:
        cookies = [{"name": SESSION_COOKIE, "value": "forged", "domain": LOOPBACK_HOST, "path": "/", "secure": True}]
    person.context.add_cookies(cookies)

    person.goto(f"{e2e_server.base_url}/")

    expect(person).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    expect(person.get_by_text(START_PAGE_LINE)).to_have_count(0)
