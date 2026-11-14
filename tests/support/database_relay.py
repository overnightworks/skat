import contextlib
import socket
import threading
from enum import Enum, auto
from typing import Self

from sqlalchemy.engine import make_url

# The Postgres message that ends a connection's start: the server is ready for the first query.
READY_FOR_QUERY = b"Z\x00\x00\x00\x05I"
CHUNK_BYTES = 65_536


class RelayMode(Enum):
    FORWARD = auto()
    REFUSE = auto()
    STALL = auto()


class DatabaseRelay:
    """A TCP relay in front of a test database, which a test turns to the faults of a database's network.

    `refuse` closes each new connection at once. `stall` lets each new connection start and then answers nothing on
    it, as a server does that stops responding after it accepted a client. `forward` lets everything through again;
    a connection that stalled stays stalled. `serve_as` sends the connections that follow to another database of
    the same server.
    """

    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        self._upstream = (url.host or "127.0.0.1", url.port or 5432)
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.url = url.set(host="127.0.0.1", port=self._listener.getsockname()[1]).render_as_string(hide_password=False)
        self._mode = RelayMode.FORWARD
        self._substitution: tuple[bytes, bytes] | None = None
        self._sockets: set[socket.socket] = set()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._start(self._accept)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exit: object) -> None:
        self.close()

    def refuse(self) -> None:
        self._mode = RelayMode.REFUSE

    def stall(self) -> None:
        self._mode = RelayMode.STALL

    def forward(self) -> None:
        self._mode = RelayMode.FORWARD

    def serve_as(self, asked: str, served: str) -> None:
        """Sends the connections that ask for database `asked` to `served`; the names are of one length."""
        assert len(asked) == len(served)  # noqa: S101 - the startup message is rewritten in place
        self._substitution = (b"database\x00" + asked.encode() + b"\x00", b"database\x00" + served.encode() + b"\x00")

    def close(self) -> None:
        self._shut(self._listener)
        with self._lock:
            sockets = list(self._sockets)
            threads = list(self._threads)
        for connection in sockets:
            self._shut(connection)
        for thread in threads:
            thread.join()

    def _start(self, target, *arguments: object) -> None:
        thread = threading.Thread(target=target, args=arguments, daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def _track(self, connection: socket.socket) -> None:
        with self._lock:
            self._sockets.add(connection)

    @staticmethod
    def _shut(connection: socket.socket) -> None:
        with contextlib.suppress(OSError):
            connection.shutdown(socket.SHUT_RDWR)
        connection.close()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            self._track(client)
            if self._mode is RelayMode.REFUSE:
                self._shut(client)
                continue
            try:
                server = socket.create_connection(self._upstream)
            except OSError:
                self._shut(client)
                continue
            self._track(server)
            stalled = threading.Event()
            self._start(self._pump, client, server, stalled, False)
            self._start(self._pump, server, client, stalled, True)

    def _pump(self, source: socket.socket, target: socket.socket, stalled: threading.Event, from_server: bool) -> None:
        while True:
            try:
                chunk = source.recv(CHUNK_BYTES)
            except OSError:
                chunk = b""
            if not chunk:
                self._shut(target)
                return
            if stalled.is_set():
                continue
            if not from_server and self._substitution is not None:
                chunk = chunk.replace(*self._substitution)
            if from_server and self._mode is RelayMode.STALL and READY_FOR_QUERY in chunk:
                chunk = chunk[: chunk.index(READY_FOR_QUERY) + len(READY_FOR_QUERY)]
                stalled.set()
            try:
                target.sendall(chunk)
            except OSError:
                return
