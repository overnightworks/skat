"""A call page around a Skat table, as hopin's page frames it, and Skat served on the site they share."""

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING

from skat.web.constants import CALL_MODE, MODE_QUERY_NAME
from tests.e2e.support.server import loopback_sign_in, running_skat
from tests.e2e.support.tables import open_new_table

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from playwright.sync_api import Page, Route

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

# One site, as hopin and Skat share one in production: a frame of another site gets no session cookie.
SKAT_HOST = "skat.frame.localhost"
CALL_HOST = "call.frame.localhost"
OTHER_HOST = "other.frame.localhost"
# Nothing listens on either port: the page routes answer the call host.
CALL_PORT = 8444
OTHER_PORT = CALL_PORT + 1
CALL_ORIGIN = f"https://{CALL_HOST}:{CALL_PORT}"
HTTP_OK = 200
# Chromium's console line for a frame its content security policy refused.
FRAME_REFUSED = "frame-ancestors"
# The attributes hopin's call page puts on the frame that holds a Skat table.
CALL_FRAME_ATTRIBUTES = (
    'sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" '
    'allow="" referrerpolicy="no-referrer"'
)
FRAME = "#stage"
CHAIR = ".chair"
THREE_CHAIRS = 3


def serve_on_the_frame_site(
    e2e_server: RunningServer, directory: Path, **overrides: str | None
) -> Iterator[RunningServer]:
    loopback = loopback_sign_in(directory, SKAT_HOST, **overrides)
    tls = directory / "tls"
    tls.mkdir()
    with running_skat(loopback, tls, e2e_server.engine) as server:
        yield server


@contextmanager
def served_from(origin: str, page: Page, browser_coverage: BrowserCoverage, body: str) -> Iterator[None]:
    """Answer the page's navigations to `origin` with `body`; no server stands there."""

    def answer(route: Route) -> None:
        if not browser_coverage.cancel_take_reissue(route):
            route.fulfill(status=HTTP_OK, content_type="text/html", body=body)

    page.route(f"{origin}/**", answer)
    yield
    page.unroute(f"{origin}/**", answer)


def table_url(server: RunningServer, path: str) -> str:
    return f"{server.base_url}{path}?{MODE_QUERY_NAME}={CALL_MODE}"


def page_holding(frame_address: str, style: str = "") -> str:
    return (
        f'<!doctype html><title>call</title><iframe id="stage" src="{frame_address}" style="{style}" '
        f"{CALL_FRAME_ATTRIBUTES}></iframe>"
    )


# The greeting call page's script: it records what the Skat frame posts, greets every `ready` when asked, and lets a
# test send one message to the frame (`sendToStage`) or the valid greeting (`greet`) itself.
_GREETING_SCRIPT = """
window.messages = [];
window.greetEveryReady = GREET_EVERY_READY;
const stage = () => document.getElementById("stage").contentWindow;
window.sendToStage = (data) => stage().postMessage(data, SKAT_ORIGIN);
window.greet = () => sendToStage({ v: 1, type: "hello", attachment: 1, attempt: null });
addEventListener("message", (event) => {
    if (event.source !== stage() || event.origin !== SKAT_ORIGIN) return;
    messages.push(event.data);
    if (greetEveryReady) greet();
});
"""


def greeting_page_holding(frame_address: str, skat_origin: str, *, greets_every_ready: bool = False) -> str:
    """The call page of `page_holding`, recording the frame's messages and greeting as the call page does."""
    script = _GREETING_SCRIPT.replace("SKAT_ORIGIN", json.dumps(skat_origin)).replace(
        "GREET_EVERY_READY", json.dumps(greets_every_ready)
    )
    return page_holding(frame_address) + f"<script>{script}</script>"


def new_table(open_person: Callable[..., Page], server: RunningServer) -> str:
    return open_new_table(open_person(server=server), server)
