"""A stand-in for the edge in front of Skat: a TLS proxy that cuts silent responses and answers 502 while Skat is down.

The edge provider cuts a response that writes nothing for a read timeout, and answers 502 when the origin refuses
connections, as during a release. The stand-in does both, with a timeout a test can shorten.
"""

import asyncio
import ssl
import threading
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.store.migrate import create_store_engine
from tests.e2e.support.server import (
    LOOPBACK_HOST,
    RunningServer,
    loopback_sign_in,
    reserve_free_port,
    running_skat,
    write_self_signed_certificate,
)
from tests.support.postgres import created_database, migrated_template

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pytest

BAD_GATEWAY: Final = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
READ_SIZE: Final = 65536
REQUEST_HEAD_SECONDS: Final = 5
THREAD_STOP_SECONDS: Final = 10
START_SECONDS: Final = 10


async def _relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle_seconds: float | None) -> bool:
    """Copies bytes until the reader ends; true when `idle_seconds` passed with nothing read, which cuts the copy."""
    with suppress(OSError):
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(READ_SIZE), idle_seconds)
            except TimeoutError:
                return True
            if not chunk:
                return False
            writer.write(chunk)
            await writer.drain()
    return False


async def _answer_bad_gateway(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    with suppress(OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), REQUEST_HEAD_SECONDS)
    with suppress(OSError):
        writer.write(BAD_GATEWAY)
        await writer.drain()
    writer.close()


class Edge:
    """Listens on `port` with Skat's certificate, relays to Skat on `backend_port`, and counts what it did."""

    def __init__(self, port: int, backend_port: int, idle_cut_seconds: float, certificate_directory: Path) -> None:
        self.port = port
        self.idle_cuts = 0
        self.bad_gateways = 0
        self._backend_port = backend_port
        self._idle_cut_seconds = idle_cut_seconds
        self._certificate_directory = certificate_directory
        self._started = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=asyncio.run, args=(self._serve(),), daemon=True)
        self._thread.start()
        if not self._started.wait(START_SECONDS):
            message = f"the edge did not listen within {START_SECONDS} seconds"
            raise RuntimeError(message)

    def stop(self) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=THREAD_STOP_SECONDS)

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        key_file, certificate_file = write_self_signed_certificate(self._certificate_directory)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certificate_file, key_file)
        server = await asyncio.start_server(self._handle, LOOPBACK_HOST, self.port, ssl=server_context)
        self._started.set()
        await self._stop.wait()
        server.close()

    async def _handle(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                LOOPBACK_HOST, self._backend_port, ssl=_backend_context()
            )
        except OSError:
            self.bad_gateways += 1
            await _answer_bad_gateway(client_reader, client_writer)
            return
        to_backend = asyncio.ensure_future(_relay(client_reader, backend_writer, None))
        to_client = asyncio.ensure_future(_relay(backend_reader, client_writer, self._idle_cut_seconds))
        done, pending = await asyncio.wait({to_backend, to_client}, return_when=asyncio.FIRST_COMPLETED)
        if to_client in done and to_client.result():
            self.idle_cuts += 1
        for task in pending:
            task.cancel()
        client_writer.close()
        backend_writer.close()


def _backend_context() -> ssl.SSLContext:
    # Skat's certificate is self-signed for the loopback address, and only the browser's trust is at stake here.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


@dataclass(frozen=True)
class BehindEdge:
    server: RunningServer
    edge: Edge


@contextmanager
def skat_behind_an_edge(
    directories: pytest.TempPathFactory, *, heartbeat_seconds: float, idle_cut_seconds: float
) -> Iterator[BehindEdge]:
    """Skat on a free port behind an edge stand-in, which the pages address as Skat's public origin.

    `heartbeat_seconds` is Skat's stream tick and `idle_cut_seconds` the silence the edge cuts a response after.
    """
    edge_port = reserve_free_port()
    loopback = loopback_sign_in(directories.mktemp("sign-in"), public_origin=f"https://{LOOPBACK_HOST}:{edge_port}")
    # Skat listens on its own port; the pages reach it through the edge, so their address is the edge's port.
    public = replace(loopback, port=edge_port)
    edge = Edge(edge_port, loopback.port, idle_cut_seconds, directories.mktemp("edge-tls"))
    with migrated_template() as template, created_database(template) as database_url:
        engine = create_store_engine(database_url)
        try:
            with running_skat(public, directories.mktemp("tls"), engine, heartbeat_seconds=heartbeat_seconds) as server:
                edge.start()
                try:
                    yield BehindEdge(server, edge)
                finally:
                    edge.stop()
        finally:
            engine.dispose()
