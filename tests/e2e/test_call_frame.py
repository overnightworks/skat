from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.e2e.support.server import loopback_sign_in, reserve_free_port, running_skat
from tests.e2e.support.tables import open_new_table, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from playwright.sync_api import Page, Route

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

# One site, as hopin and Skat share one in production: a frame of another site gets no session cookie.
SKAT_HOST = "skat.frame.localhost"
CALL_HOST = "call.frame.localhost"
OTHER_HOST = "other.frame.localhost"
HTTP_OK = 200
HTTP_FORBIDDEN = 403
# The attributes hopin's call page puts on the frame that holds a Skat table.
CALL_FRAME_ATTRIBUTES = (
    'sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" '
    'allow="" referrerpolicy="no-referrer"'
)
# Chromium's console line for a frame its content security policy refused.
FRAME_REFUSED = "frame-ancestors"
CHAIR = ".chair"
THREE_CHAIRS = 3
# A simple request: no preflight stops it, so it reaches the server whatever the origin.
SIMPLE_POST = """([url, body]) => fetch(url, {
    method: "POST", mode: "no-cors", credentials: "include", headers: {"content-type": "text/plain"}, body
}).then(() => undefined)"""


@pytest.fixture(scope="module")
def call_origin() -> str:
    return f"https://{CALL_HOST}:{reserve_free_port()}"


def serve_on_the_frame_site(
    e2e_server: RunningServer, directory: Path, **overrides: str | None
) -> Iterator[RunningServer]:
    loopback = loopback_sign_in(directory, SKAT_HOST, **overrides)
    tls = directory / "tls"
    tls.mkdir()
    with running_skat(loopback, tls, e2e_server.engine) as server:
        yield server


@pytest.fixture(scope="module")
def framing_server(
    e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory, call_origin: str
) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("framing"), call_origin=call_origin)


@pytest.fixture(scope="module")
def unframed_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("unframed"))


@contextmanager
def served_from(origin: str, page: Page, browser_coverage: BrowserCoverage, body: str) -> Iterator[None]:
    """Answer the page's navigations to `origin` with `body`; no server stands there."""

    def answer(route: Route) -> None:
        if not browser_coverage.cancel_take_reissue(route):
            route.fulfill(status=HTTP_OK, content_type="text/html", body=body)

    page.route(f"{origin}/**", answer)
    yield
    page.unroute(f"{origin}/**", answer)


CALL_PAGE_WITHOUT_FRAME = "<!doctype html><title>call</title>"


def table_url(server: RunningServer, path: str) -> str:
    return f"{server.base_url}{path}?mode=call"


def page_holding(frame_address: str) -> str:
    return (
        f'<!doctype html><title>call</title><iframe id="stage" src="{frame_address}" {CALL_FRAME_ATTRIBUTES}></iframe>'
    )


def new_table(open_person: Callable[..., Page], server: RunningServer) -> str:
    return open_new_table(open_person(server=server), server)


def table_answer(person: Page, server: RunningServer, path: str) -> dict[str, object]:
    return person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id_of(path)}").json()


REFUSED_FRAMES = [
    pytest.param("unframed_server", lambda call_origin: call_origin, id="unset-setting"),
    pytest.param("framing_server", lambda _call_origin: f"https://{OTHER_HOST}:{reserve_free_port()}", id="other-host"),
    pytest.param("framing_server", lambda _call_origin: f"https://{CALL_HOST}:{reserve_free_port()}", id="other-port"),
]


@pytest.mark.parametrize(("server_name", "framing_origin"), REFUSED_FRAMES)
def test_a_table_stays_out_of_every_frame_but_the_configured_call_origins(
    request: pytest.FixtureRequest,
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    expected_request_failures: list[str],
    call_origin: str,
    server_name: str,
    framing_origin: Callable[[str], str],
) -> None:
    server: RunningServer = request.getfixturevalue(server_name)
    path = new_table(open_person, server)
    expected_request_failures.append(table_url(server, path))
    origin = framing_origin(call_origin)
    visitor = open_person(server=server)

    with (
        served_from(origin, visitor, browser_coverage, page_holding(table_url(server, path))),
        visitor.expect_console_message(lambda message: FRAME_REFUSED in message.text),
    ):
        visitor.goto(f"{origin}/")

    expect(visitor.locator("#stage")).to_be_attached()
    expect(visitor.frame_locator("#stage").locator(CHAIR)).to_have_count(0)


def test_the_call_origin_shows_the_table_signed_in_and_the_frame_reads_and_streams_as_the_page_does(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    call_origin: str,
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)
    read_address = f"{framing_server.base_url}{TABLES_PATH}/{table_id_of(path)}"

    with served_from(call_origin, visitor, browser_coverage, page_holding(table_url(framing_server, path))):
        with (
            visitor.expect_response(lambda response: response.url == read_address) as read,
            visitor.expect_response(lambda response: response.url == read_address + TABLE_EVENTS_SUFFIX) as stream,
        ):
            visitor.goto(f"{call_origin}/")
        expect(visitor.frame_locator("#stage").locator(CHAIR)).to_have_count(THREE_CHAIRS)

    assert (read.value.status, stream.value.status) == (HTTP_OK, HTTP_OK)


def test_a_request_the_call_page_sends_to_skat_is_refused_and_takes_no_chair(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    call_origin: str,
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)
    before = table_answer(visitor, framing_server, path)
    sit_address = f"{framing_server.base_url}{TABLES_PATH}/{table_id_of(path)}{TABLE_SIT_SUFFIX}"

    with served_from(call_origin, visitor, browser_coverage, CALL_PAGE_WITHOUT_FRAME):
        visitor.goto(f"{call_origin}/")
        with visitor.expect_response(lambda response: response.url == sit_address) as sit:
            visitor.evaluate(SIMPLE_POST, [sit_address, '{"command_id": "call-sit-0001", "seat": 1}'])

    assert sit.value.status == HTTP_FORBIDDEN
    after = table_answer(visitor, framing_server, path)
    assert (after["version"], after["chairs"]) == (before["version"], before["chairs"])
