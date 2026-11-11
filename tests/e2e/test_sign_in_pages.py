from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.constants import AUTH_CALLBACK_PATH, LOGIN_PATH, NO_ACCESS_PATH
from tests.e2e.support.browser import LEGAL_LINKS, record_page_errors
from tests.e2e.support.people import FORM_FACTORS
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

FORGED_CALLBACK = f"{AUTH_CALLBACK_PATH}?state=forged&code=x"
SIGN_IN_PAGES = [
    pytest.param(LOGIN_PATH, 200, "Log in", id="signed-out"),
    pytest.param(FORGED_CALLBACK, 403, "Try again", id="login-failed"),
    pytest.param(NO_ACCESS_PATH, 200, "Log out", id="no-access"),
]


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
@pytest.mark.parametrize(("path", "status", "action"), SIGN_IN_PAGES)
def test_each_sign_in_page_names_skat_offers_its_one_action_and_links_both_legal_texts(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    path: str,
    status: int,
    action: str,
) -> None:
    person = record_page_errors(
        open_person(signed_in=False, **form_factor), page_errors, console=status == HTTPStatus.OK
    )

    response = person.goto(f"{e2e_server.base_url}{path}")

    assert response is not None
    assert response.status == status
    expect(person).to_have_title(catalog_text("appName"))
    expect(person.get_by_role("heading", level=1)).to_be_visible()
    expect(person.get_by_text(catalog_text("appName")).first).to_be_visible()
    action_element = person.get_by_role("link", name=action, exact=True).or_(
        person.get_by_role("button", name=action, exact=True)
    )
    expect(action_element).to_have_count(1)
    for key, href in LEGAL_LINKS.items():
        expect(person.get_by_role("link", name=catalog_text(key))).to_have_attribute("href", href)
    expect(person.locator("body")).to_have_css("margin", "0px")
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
