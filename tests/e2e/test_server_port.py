import http.client
import socket
from contextlib import suppress
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest

from skat.store.migrate import create_store_engine
from tests.e2e.support.edge import Edge
from tests.e2e.support.raw_http import self_signed_tolerant_context
from tests.e2e.support.server import (
    LOOPBACK_HOST,
    listener_port,
    listening_loopback_socket,
    loopback_sign_in,
    running_skat,
)
from tests.support.postgres import created_database, migrated_template

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e


def get_status(base_url: str, path: str) -> int:
    parts = urlsplit(base_url)
    connection = http.client.HTTPSConnection(parts.hostname or "", parts.port, context=self_signed_tolerant_context())
    try:
        connection.request("GET", path)
        return connection.getresponse().status
    finally:
        connection.close()


def go_for_port(competitor: socket.socket, port: int) -> None:
    """What another process does with a port it finds free: take it and listen."""
    competitor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with suppress(OSError):
        competitor.bind((LOOPBACK_HOST, port))
        competitor.listen()


def test_skat_starts_though_another_process_goes_for_its_port_between_choosing_and_serving(tmp_path: Path) -> None:
    sign_in_directory = tmp_path / "sign-in"
    tls_directory = tmp_path / "tls"
    sign_in_directory.mkdir()
    tls_directory.mkdir()
    loopback = loopback_sign_in(sign_in_directory)
    with socket.socket() as competitor:
        go_for_port(competitor, loopback.port)
        with (
            migrated_template() as template,
            created_database(template) as database_url,
        ):
            engine = create_store_engine(database_url)
            try:
                with running_skat(loopback, tls_directory, engine) as server:
                    assert get_status(server.base_url, "/") < http.HTTPStatus.INTERNAL_SERVER_ERROR
            finally:
                engine.dispose()


def test_the_edge_listens_though_another_process_goes_for_its_port_between_choosing_and_serving(tmp_path: Path) -> None:
    listener = listening_loopback_socket()
    edge = Edge(listener, backend_port=1, idle_cut_seconds=1, certificate_directory=tmp_path)
    with socket.socket() as competitor:
        go_for_port(competitor, edge.port)
        edge.start()
        try:
            with (
                socket.create_connection((LOOPBACK_HOST, listener_port(listener))) as client,
                self_signed_tolerant_context().wrap_socket(client) as tls_client,
            ):
                assert tls_client.version() is not None
        finally:
            edge.stop()
