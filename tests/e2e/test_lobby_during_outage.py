from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.constants import VERSION_FILE_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON
from tests.e2e.support.edge import BehindEdge, skat_behind_an_edge
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.tables import open_new_table, watch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

RECONNECTING = text(SOURCE_LANGUAGE, "app.reconnecting")
UNREACHABLE = text(SOURCE_LANGUAGE, "app.unreachable")
LOBBY = text(SOURCE_LANGUAGE, "table.lobby")
HEARTBEAT_SECONDS = 1.0
IDLE_CUT_SECONDS = 30.0
BACK_SECONDS = 30_000
A_MINUTE_AND_MORE_MILLISECONDS = 70_000
START_PAGE_CODE = "**/_app/immutable/nodes/*.js"
THROWING_CODE = "throw new Error('the start page has a defect');"
ROUTE_THAT_DOES_NOT_EXIST = "/no-such-page"


@pytest.fixture
def behind_edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[BehindEdge]:
    with skat_behind_an_edge(
        tmp_path_factory, heartbeat_seconds=HEARTBEAT_SECONDS, idle_cut_seconds=IDLE_CUT_SECONDS
    ) as behind:
        yield behind


@pytest.fixture
def e2e_server(behind_edge: BehindEdge) -> RunningServer:
    return behind_edge.server


def notice(person: Page):
    return person.get_by_role("status").filter(has_text=RECONNECTING)


def sit_cold_at_a_table(open_person: Callable[..., Page], server: RunningServer, form_factor: dict[str, Any]) -> Page:
    """A person on a table page whose document is new, so that the start page's code has not been loaded."""
    host = open_person(server=server, **form_factor)
    path = open_new_table(host, server)
    guest = open_person(server=server, **form_factor)
    guest.clock.install()
    watch(guest, server, path)
    guest.evaluate("window.sameDocument = true")
    return guest


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_tapping_lobby_while_skat_is_away_shows_the_notice_and_opens_the_lobby_when_skat_is_back(
    open_person: Callable[..., Page], behind_edge: BehindEdge, form_factor: dict[str, Any]
) -> None:
    server = behind_edge.server
    person = sit_cold_at_a_table(open_person, server, form_factor)

    server.stop()
    person.get_by_role("link", name=LOBBY).click()

    expect(person).to_have_url(f"{server.base_url}/")
    expect(notice(person)).to_be_visible()
    expect(person.locator(".room")).to_have_count(0)
    expect(person.get_by_text("Internal Error")).to_have_count(0)
    expect(person.get_by_text(UNREACHABLE)).to_have_count(0)
    person.clock.fast_forward(A_MINUTE_AND_MORE_MILLISECONDS)
    expect(person.get_by_text(UNREACHABLE)).to_be_visible()
    expect(notice(person)).to_be_visible()
    expect(person.get_by_role("button")).to_have_count(0)
    expect(person.get_by_role("link")).to_have_count(0)
    server.start()

    expect(person.get_by_role("button", name=NEW_TABLE_BUTTON)).to_be_visible(timeout=BACK_SECONDS)
    expect(notice(person)).to_have_count(0)
    expect(person.get_by_text(UNREACHABLE)).to_have_count(0)
    assert person.evaluate("window.sameDocument") is True


def test_a_start_page_that_fails_though_the_edge_answers_ends_in_its_status_and_message_without_looping(
    open_person: Callable[..., Page], behind_edge: BehindEdge
) -> None:
    person = sit_cold_at_a_table(open_person, behind_edge.server, PHONE)
    probes: list[str] = []
    person.on(
        "request", lambda request: probes.append(request.url) if request.url.endswith(VERSION_FILE_PATH) else None
    )
    person.route(START_PAGE_CODE, lambda route: route.fulfill(content_type="text/javascript", body=THROWING_CODE))
    person.get_by_role("link", name=LOBBY).click()

    expect(person.get_by_role("heading", name="500")).to_be_visible(timeout=BACK_SECONDS)
    expect(person.get_by_text("Internal Error")).to_be_visible()
    expect(notice(person)).to_have_count(0)
    probes_when_it_stopped = len(probes)
    person.clock.fast_forward(A_MINUTE_AND_MORE_MILLISECONDS)
    person.wait_for_timeout(1000)
    assert len(probes) == probes_when_it_stopped


def test_a_route_that_does_not_exist_shows_its_status_and_message_and_no_notice(
    open_person: Callable[..., Page], behind_edge: BehindEdge
) -> None:
    server = behind_edge.server
    person = open_person(server=server, **PHONE)
    # A host that answers every address with the app's page, as a static host does, leaves the 404 to the app.
    person.route(
        f"{server.base_url}{ROUTE_THAT_DOES_NOT_EXIST}",
        lambda route: route.fulfill(response=route.fetch(url=f"{server.base_url}/")),
    )

    person.goto(f"{server.base_url}{ROUTE_THAT_DOES_NOT_EXIST}")

    expect(person.get_by_role("heading", name="404")).to_be_visible()
    expect(person.get_by_text("Not Found")).to_be_visible()
    expect(notice(person)).to_have_count(0)
