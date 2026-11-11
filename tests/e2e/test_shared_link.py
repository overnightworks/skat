import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

from skat.web.constants import LOGIN_PATH, NO_ACCESS_PATH
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors, sign_in_at_issuer
from tests.e2e.support.people import DESKTOP, FORM_FACTORS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e


NEVER_OPENED_ID = "f" * 32


def table_opened_by(opener: Page, server: RunningServer) -> str:
    """The page path of a table the signed-in opener creates through the API from the app's own origin."""
    opener.goto(f"{server.base_url}/")
    table_id = opener.evaluate(
        """async (path) => {
            const response = await fetch(path, {
                method: "POST",
                headers: {"content-type": "application/json"},
                body: JSON.stringify({command_id: crypto.randomUUID(), series_length: 36}),
            });
            return (await response.json()).id;
        }""",
        TABLES_PATH,
    )
    return f"{TABLE_PAGE_PREFIX}{table_id}"


def follow_a_shared_link_and_sign_in(
    visitor: Page, server: RunningServer, path: str, *, username: str, groups: list[str] | None = None
) -> None:
    sign_in_at_issuer(visitor, server, username=username, groups=groups)
    visitor.goto(f"{server.base_url}{path}")
    expect(visitor).to_have_url(re.compile(rf"{re.escape(LOGIN_PATH)}\?"))
    visitor.get_by_role("link", name="Log in", exact=True).click()


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_signed_out_member_signs_in_through_a_shared_link_and_lands_at_the_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = table_opened_by(opener, e2e_server)
    visitor = record_page_errors(open_person(signed_in=False, **form_factor), page_errors)

    follow_a_shared_link_and_sign_in(visitor, e2e_server, path, username="ben")

    expect(visitor).to_have_url(f"{e2e_server.base_url}{path}")
    expect(visitor.get_by_text(text(SOURCE_LANGUAGE, "table.waitingForPlayers"))).to_be_visible()
    expect(visitor.locator(".chair[data-seat='1'] .plate")).to_contain_text("anna")


def test_a_signed_out_member_signs_in_through_a_link_to_an_unknown_table_and_sees_it_is_not_found(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    # The 404 the browser logs for the table request is the console error, so only script errors are recorded.
    visitor = record_page_errors(open_person(signed_in=False, **DESKTOP), page_errors, console=False)

    follow_a_shared_link_and_sign_in(visitor, e2e_server, f"{TABLE_PAGE_PREFIX}{NEVER_OPENED_ID}", username="ben")

    expect(visitor).to_have_url(f"{e2e_server.base_url}{TABLE_PAGE_PREFIX}{NEVER_OPENED_ID}")
    expect(visitor.get_by_role("heading", name=text(SOURCE_LANGUAGE, "closed.notFound"))).to_be_visible()


def test_a_signed_out_person_the_group_does_not_admit_reaches_the_no_access_page_and_no_table_data(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = table_opened_by(opener, e2e_server)
    outsider = record_page_errors(open_person(signed_in=False, **DESKTOP), page_errors)

    follow_a_shared_link_and_sign_in(outsider, e2e_server, path, username="carl", groups=["/apps/other"])

    expect(outsider.get_by_role("button", name="Log out")).to_be_visible()
    assert urlsplit(outsider.url).path == NO_ACCESS_PATH
    expect(outsider.get_by_text(text(SOURCE_LANGUAGE, "table.waitingForPlayers"))).to_have_count(0)
    expect(outsider.locator(".chair")).to_have_count(0)
