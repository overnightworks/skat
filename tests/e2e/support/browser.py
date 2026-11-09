from typing import TYPE_CHECKING

from skat.web.constants import ACCOUNT_PATH, AUTH_CALLBACK_PATH, AUTH_START_PATH, LOGIN_GROUP
from tests.e2e.support.words import catalog_text
from tests.support.sign_in_settings import TEST_ISSUER

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage, Page, Route

    from tests.e2e.support.server import RunningServer

LEGAL_LINKS = {
    "Impressum": "https://hallucinai.de/impressum#skat",
    "Datenschutz": "https://hallucinai.de/datenschutz#skat",
    "Nutzungsbedingungen": "https://hallucinai.de/nutzungsbedingungen#skat",
}
ISSUER_END_SESSION_URL = f"{TEST_ISSUER}/protocol/openid-connect/logout"
ACCOUNT_AVATAR = ".account-button"
ACCOUNT_MENU = "#accountMenu"
# Chromium words a 401 answer to a fetch like this, and names the address in the message location.
SIGNED_OUT_ANSWER_LINE = "Failed to load resource: the server responded with a status of 401 (Unauthorized)"
NEW_TABLE_BUTTON = catalog_text("newTable")


def record_page_errors(
    page: Page, page_errors: list[str], *, console: bool = True, signed_out_account_check_origin: str | None = None
) -> Page:
    """Every script error and, with `console`, every console error or warning (a policy violation among them).

    A flow that runs the sign-in re-check names the origin it asks: the 401 the account path answers a signed-out
    person there is the re-check's truthful answer, and no other line or status at that address passes.
    """
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    if console:
        signed_out_answer = (
            None
            if signed_out_account_check_origin is None
            else (f"{signed_out_account_check_origin}{ACCOUNT_PATH}", SIGNED_OUT_ANSWER_LINE)
        )

        def record(message: ConsoleMessage) -> None:
            if message.type not in {"error", "warning"}:
                return
            if signed_out_answer == (message.location["url"], message.text):
                return
            page_errors.append(f"{message.type}: {message.text}")

        page.on("console", record)
    return page


def sign_in_at_issuer(page: Page, server: RunningServer, *, username: str, groups: list[str] | None = None) -> None:
    """Answer the sign-in start like a person who signs in at the issuer, without leaving Skat's origin.

    The start's own answer is kept, so its pending-login cookie reaches the browser, and only its redirect
    to the issuer is swapped for the callback the issuer would send the browser to. The person signs in as
    `username` in the Skat group unless `groups` names others. The route is on the page's context, so a window
    the page opens signs in the same way. Playwright routes only the first request of a navigation, so the person
    starts the sign-in from a page with a link or by opening the start path.
    """

    def answer(route: Route) -> None:
        started = route.fetch(max_redirects=0)
        query = server.issuer.authorize(
            started.headers["location"],
            subject=f"subject-{username}",
            groups=[LOGIN_GROUP] if groups is None else groups,
            username=username,
        )
        route.fulfill(
            response=started,
            status=303,
            headers={**started.headers, "location": f"{server.base_url}{AUTH_CALLBACK_PATH}?{query}"},
        )

    page.context.route(f"**{AUTH_START_PATH}**", answer)
