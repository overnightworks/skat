import http.client
import logging
import socket
import threading
import time
from contextlib import closing

from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.host.main import streams_ending_server, uvicorn_options
from skat.table.records import Actor, CreateTable
from skat.web.constants import GRACEFUL_SHUTDOWN_SECONDS
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build
from tests.support.signed_in import cookie_header, seed_member

LOOPBACK_HOST = "127.0.0.1"
STARTED_WITHIN_SECONDS = 10


class CollectingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind((LOOPBACK_HOST, 0))
        return int(probe.getsockname()[1])


def test_stopping_the_server_with_streams_open_on_several_tables_ends_them_all_and_logs_no_error(sign_in_settings):
    port = free_port()
    settings = sign_in_settings(host=LOOPBACK_HOST, port=port).settings
    stores = in_memory_stores()
    tables = in_memory_tables()
    app = create_app(
        settings, page_build=fixture_page_build(), tables=tables, rule_sets=in_memory_rule_sets(), stores=stores
    )
    member = seed_member(stores, installed_web_auth_config(app))
    owner = Actor(account_id=member.account.id, display_name=member.account.username)
    table_ids = [tables.create(owner, CreateTable(command_id=f"command-{number}")).id for number in range(3)]
    server = streams_ending_server(app, **uvicorn_options(settings))
    thread = threading.Thread(target=server.run, daemon=True)
    # uvicorn's own logging setup stops its loggers from propagating, so the handler goes on its logger.
    logged = CollectingHandler()
    logging.getLogger("uvicorn.error").addHandler(logged)

    thread.start()
    deadline = time.monotonic() + STARTED_WITHIN_SECONDS
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    connections = []
    try:
        for table_id in table_ids:
            connection = http.client.HTTPConnection(LOOPBACK_HOST, port, timeout=STARTED_WITHIN_SECONDS)
            connection.request(
                "GET",
                f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}",
                headers={"cookie": cookie_header(member.set_cookie_headers)},
            )
            answer = connection.getresponse()
            assert (answer.status, answer.readline().startswith(b"data: ")) == (200, True)
            connections.append(answer)

        stopping = time.monotonic()
        server.should_exit = True
        thread.join(timeout=STARTED_WITHIN_SECONDS)
        stopped_after = time.monotonic() - stopping
        rest = [answer.read() for answer in connections]
    finally:
        server.should_exit = True
        thread.join(timeout=STARTED_WITHIN_SECONDS)
        logging.getLogger("uvicorn.error").removeHandler(logged)

    assert not thread.is_alive()
    assert stopped_after < GRACEFUL_SHUTDOWN_SECONDS
    assert rest == [b"\n"] * len(table_ids)
    assert [record.getMessage() for record in logged.records if record.levelno >= logging.ERROR] == []
