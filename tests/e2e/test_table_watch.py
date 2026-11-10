import http.client
import json
import threading
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.records import Actor, CreateTable
from skat.table.service import TableService
from skat.web.constants import GRACEFUL_SHUTDOWN_SECONDS
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.raw_http import self_signed_tolerant_context
from tests.e2e.support.server import LOOPBACK_HOST, loopback_sign_in, running_skat
from tests.e2e.support.tables import open_new_table, table_id_of
from tests.e2e.support.words import catalog_text
from tests.support.signed_in import cookie_header, new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e


SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
FIRST_EVENT = """(url) => new Promise((resolve) => {
    const source = new EventSource(url);
    source.onmessage = (event) => { source.close(); resolve(event.data); };
})"""
RECONNECTING = catalog_text("reconnecting")
# The browser asks again a few seconds after a failed stream.
RECONNECT_TIMEOUT_MILLISECONDS = 15_000


def watchers_of(person: Page):
    return person.locator(".watchers span")


def table_version(server: RunningServer, path: str) -> int:
    with server.engine.connect() as connection:
        query = text("SELECT version FROM tables WHERE id = :id")
        return int(connection.execute(query, {"id": table_id_of(path)}).scalar_one())


def watch(person: Page, server: RunningServer, path: str) -> None:
    person.goto(f"{server.base_url}{path}")
    expect(person.locator(".chair")).to_have_count(3)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_members_who_open_a_table_change_the_count_on_every_open_page_without_a_reload(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    expect(watchers_of(opener)).to_have_text("0")

    second = record_page_errors(open_person(username="ben", **form_factor), page_errors)
    watch(second, e2e_server, path)
    expect(watchers_of(opener)).to_have_text("1")
    expect(watchers_of(second)).to_have_text("1")
    third = record_page_errors(open_person(username="cleo", **form_factor), page_errors)
    watch(third, e2e_server, path)

    for person in (opener, second, third):
        expect(watchers_of(person)).to_have_text("2")
    assert opener.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_one_account_in_two_tabs_counts_once_and_a_leaving_tab_changes_the_count_only_with_the_last(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    version = table_version(e2e_server, path)
    first_tab = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(first_tab, e2e_server, path)
    expect(watchers_of(opener)).to_have_text("1")

    second_tab = record_page_errors(first_tab.context.new_page(), page_errors)
    watch(second_tab, e2e_server, path)
    expect(watchers_of(second_tab)).to_have_text("1")
    second_tab.close()
    other = record_page_errors(open_person(username="cleo", **DESKTOP), page_errors)
    watch(other, e2e_server, path)
    expect(watchers_of(opener)).to_have_text("2")

    first_tab.close()

    expect(watchers_of(opener)).to_have_text("1")
    expect(watchers_of(other)).to_have_text("1")
    assert table_version(e2e_server, path) == version


def test_a_stream_starts_with_the_full_view_built_for_its_viewer_and_names_no_account_or_watcher(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], Any],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> None:
    opener = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(opener, e2e_server)
    watcher = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(watcher, e2e_server, path)
    url = f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}"

    seen = {
        name: json.loads(person.evaluate(FIRST_EVENT, url))
        for name, person in (("opener", opener), ("watcher", watcher))
    }

    assert seen["opener"]["watchers"] == seen["watcher"]["watchers"] == 1
    assert [chair["is_mine"] for chair in seen["opener"]["chairs"]] == [True, False, False]
    assert [chair["is_mine"] for chair in seen["watcher"]["chairs"]] == [False, False, False]
    for person, event in ((opener, seen["opener"]), (watcher, seen["watcher"])):
        assert set(event) == {
            "id",
            "version",
            "chairs",
            "watchers",
            "hand",
            "passed_in",
            "result",
            "series",
            "options",
            "ended",
        }
        assert {key for chair in event["chairs"] for key in chair} == {
            "seat",
            "occupant_name",
            "occupant_kind",
            "is_mine",
            "is_away",
            "ready",
            "hand",
            "total",
        }
        assert member_of(person).account.id not in json.dumps(event)
    assert "ben" not in json.dumps(seen["opener"])


def test_a_stream_the_network_refuses_dims_the_view_with_verbinde_neu_and_the_current_view_returns_with_it(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    opener = record_page_errors(open_person(username="anna", **PHONE), page_errors, console=False)
    path = open_new_table(opener, e2e_server)
    events = f"**{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}"
    opener.route(events, lambda route: route.abort())

    opener.reload()

    expect(opener.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    expect(opener.locator(".stage.stale")).to_have_count(1)
    other = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(other, e2e_server, path)
    opener.unroute(events)

    expect(opener.get_by_text(RECONNECTING)).to_be_hidden(timeout=RECONNECT_TIMEOUT_MILLISECONDS)
    expect(opener.locator(".stale")).to_have_count(0)
    expect(watchers_of(opener)).to_have_text("1")


@pytest.mark.parametrize("form_factor", [pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")])
def test_a_stream_that_drops_after_its_view_dims_the_last_view_and_recovers_without_a_reload(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}/")
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors, console=False)
    path = open_new_table(opener, e2e_server)
    expect(watchers_of(opener)).to_have_text("0")
    events = f"**{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}"
    view = opener.evaluate(FIRST_EVENT, f"{e2e_server.base_url}{TABLES_PATH}/{table_id_of(path)}{TABLE_EVENTS_SUFFIX}")
    served: list[bool] = []

    def serve_one_view_then_refuse(route: Route) -> None:
        if served:
            route.abort()
            return
        served.append(True)
        route.fulfill(content_type="text/event-stream", body=f"data: {view}\n\n")

    opener.route(events, serve_one_view_then_refuse)
    opener.reload()
    opener.evaluate("window.sameDocument = true")

    expect(opener.get_by_role("status").filter(has_text=RECONNECTING)).to_be_visible()
    expect(opener.locator(".stage.stale")).to_have_count(1)
    expect(opener.locator(".chair")).to_have_count(3)
    other = record_page_errors(open_person(username="ben", **form_factor), page_errors)
    watch(other, e2e_server, path)
    opener.unroute(events)

    expect(opener.get_by_text(RECONNECTING)).to_be_hidden(timeout=RECONNECT_TIMEOUT_MILLISECONDS)
    expect(opener.locator(".stale")).to_have_count(0)
    expect(watchers_of(opener)).to_have_text("1")
    assert opener.evaluate("window.sameDocument === true")


def test_stopping_the_server_ends_every_open_stream_within_its_stop_time(
    e2e_server: RunningServer, tmp_path: Path
) -> None:
    loopback = loopback_sign_in(tmp_path)
    tls = tmp_path / "tls"
    tls.mkdir()
    tables = TableService(PostgresTableTransactions(e2e_server.engine))
    ended = threading.Event()

    def read_until_the_stream_ends(response: http.client.HTTPResponse) -> None:
        try:
            while response.readline():
                pass
        except OSError, http.client.HTTPException:
            pass
        ended.set()

    with running_skat(loopback, tls, e2e_server.engine) as server:
        member = seed_member(server.stores, server.config, account=new_account(server.stores, server.config))
        table = tables.create(
            Actor(account_id=member.account.id, display_name=member.account.username),
            CreateTable(command_id="stop-0001"),
        )
        connection = http.client.HTTPSConnection(
            LOOPBACK_HOST,
            loopback.port,
            context=self_signed_tolerant_context(),
        )
        connection.request(
            "GET",
            f"{TABLES_PATH}/{table.id}{TABLE_EVENTS_SUFFIX}",
            headers={"cookie": cookie_header(member.set_cookie_headers)},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.readline().startswith(b"data: ")
        reader = threading.Thread(target=read_until_the_stream_ends, args=(response,), daemon=True)
        reader.start()

    assert ended.wait(timeout=GRACEFUL_SHUTDOWN_SECONDS)
    connection.close()
