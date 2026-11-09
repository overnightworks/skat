import http.client
import json
import time
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select

from skat.store.schema import tables
from skat.table.rules import CREATE_TABLE_COMMAND
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.e2e.support.raw_http import RawSession, self_signed_tolerant_context
from tests.e2e.support.server import skat_on_new_database
from tests.support.signed_in import cookie_header, new_account, seed_member
from tests.support.table_rows import rows_of

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

EMPTY_TABLE_SECONDS = 2
ENDS_WITHIN_SECONDS = EMPTY_TABLE_SECONDS + 20
POLL_SECONDS = 0.2


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, with an empty-table wait short enough to wait out."""
    with skat_on_new_database(tmp_path_factory, empty_table_seconds=EMPTY_TABLE_SECONDS) as server:
        yield server


def signed_in(server: RunningServer) -> RawSession:
    member = seed_member(server.stores, server.config, account=new_account(server.stores, server.config))
    return RawSession(server, member)


def open_stream(server: RunningServer, person: RawSession, path: str) -> http.client.HTTPSConnection:
    """A stream left open after its first message."""
    parts = urlsplit(server.base_url)
    connection = http.client.HTTPSConnection(parts.hostname or "", parts.port, context=self_signed_tolerant_context())
    headers = {"cookie": cookie_header(person.member.set_cookie_headers), "origin": server.base_url}
    connection.request("GET", f"{path}{TABLE_EVENTS_SUFFIX}", headers=headers)
    connection.getresponse().readline()
    return connection


def test_an_undealt_table_left_by_its_only_stream_ends_and_a_dealt_one_pauses_beside_a_table_still_watched(
    e2e_server: RunningServer,
) -> None:
    anna, ben, cleo = (signed_in(e2e_server) for _ in range(3))
    left_id = json.loads(anna.post(TABLES_PATH, {"command_id": "end-create-0001"}))["id"]
    left_path = f"{TABLES_PATH}/{left_id}"
    cleo.post(f"{left_path}{TABLE_SIT_SUFFIX}", {"command_id": "end-sit-0002", "seat": 2})
    dealt_id = json.loads(anna.post(TABLES_PATH, {"command_id": "end-create-0004"}))["id"]
    dealt_path = f"{TABLES_PATH}/{dealt_id}"
    cleo.post(f"{dealt_path}{TABLE_SIT_SUFFIX}", {"command_id": "end-sit-0005", "seat": 2})
    ben.post(f"{dealt_path}{TABLE_SIT_SUFFIX}", {"command_id": "end-sit-0006", "seat": 3})
    watched_id = json.loads(ben.post(TABLES_PATH, {"command_id": "end-create-0003"}))["id"]
    watched = open_stream(e2e_server, ben, f"{TABLES_PATH}/{watched_id}")
    try:
        watched_before = rows_of(e2e_server.engine, watched_id)
        anna.first_stream_message(f"{dealt_path}{TABLE_EVENTS_SUFFIX}")
        dealt_before = rows_of(e2e_server.engine, dealt_id)
        anna.first_stream_message(f"{left_path}{TABLE_EVENTS_SUFFIX}")

        deadline = time.monotonic() + ENDS_WITHIN_SECONDS
        answer = json.loads(anna.get(left_path))
        while answer["ended"] is None and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            answer = json.loads(anna.get(left_path))

        assert answer["ended"] == {"reason": "empty", "empty_seconds": EMPTY_TABLE_SECONDS}
        assert (answer["chairs"], answer["hand"], answer["watchers"]) == ([], None, 0)
        left = rows_of(e2e_server.engine, left_id)
        assert {name for name, rows in left.items() if rows} == {"tables", "receipts"}
        assert [row[:3] for row in left["receipts"]] == [
            (anna.member.account.id, "end-create-0001", CREATE_TABLE_COMMAND)
        ]
        dealt = json.loads(anna.get(dealt_path))
        assert (dealt["ended"], dealt["hand"] is not None) == (None, True)
        assert rows_of(e2e_server.engine, dealt_id) == dealt_before
        assert rows_of(e2e_server.engine, watched_id) == watched_before
    finally:
        watched.close()


def stored_times(server: RunningServer, table_id: str) -> tuple[object, object]:
    with server.engine.connect() as connection:
        return tuple(
            connection.execute(select(tables.c.empty_since, tables.c.ended_at).where(tables.c.id == table_id)).one()
        )


def test_an_undealt_table_left_before_a_restart_ends_no_sooner_than_the_wait_after_its_leave(
    e2e_server: RunningServer,
) -> None:
    anna = signed_in(e2e_server)
    table_id = json.loads(anna.post(TABLES_PATH, {"command_id": "restart-create-0001"}))["id"]
    anna.first_stream_message(f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}")
    deadline = time.monotonic() + ENDS_WITHIN_SECONDS
    while stored_times(e2e_server, table_id)[0] is None and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    left_at = stored_times(e2e_server, table_id)[0]

    e2e_server.restart(while_stopping=lambda: None)
    anna = signed_in(e2e_server)
    answer = json.loads(anna.get(f"{TABLES_PATH}/{table_id}"))
    while answer["ended"] is None and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        answer = json.loads(anna.get(f"{TABLES_PATH}/{table_id}"))

    assert answer["ended"] == {"reason": "empty", "empty_seconds": EMPTY_TABLE_SECONDS}
    assert stored_times(e2e_server, table_id)[1] - left_at >= timedelta(seconds=EMPTY_TABLE_SECONDS)
