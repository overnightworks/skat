import datetime
import random
import socket
import threading
import time
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from webauth.config import installed_web_auth_config

from skat.host.app import UNPLAYED_SWEEP_SECONDS, create_app
from skat.host.main import streams_ending_server, uvicorn_options
from skat.store.migrate import create_store_engine
from skat.store.rule_sets import PostgresRuleSets
from skat.store.tables import PostgresTableTransactions
from skat.table.rule_sets import RuleSetService
from skat.table.service import TableService
from skat.web.constants import STREAM_HEARTBEAT_SECONDS
from skat.web.page_build import BUILD_DIRECTORY, PageBuild
from tests.support.fake_issuer import FakeIssuer
from tests.support.in_memory_stores import in_memory_stores
from tests.support.postgres import created_database, migrated_template
from tests.support.sign_in_settings import build_sign_in_settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, MutableSequence
    from pathlib import Path

    from _typeshed import SupportsLenAndGetItem
    from sqlalchemy import Engine
    from webauth.single_process_stores import SingleProcessStores

    from skat.web.presence import Scheduler
    from tests.support.sign_in_settings import SignInSettings

LOOPBACK_HOST = "127.0.0.1"

READINESS_POLL_INTERVAL_SECONDS = 0.1
READINESS_DEADLINE_SECONDS = 20
SERVER_STOP_TIMEOUT_SECONDS = 10


def listening_loopback_socket(port: int = 0) -> socket.socket:
    """A socket listening on loopback, on a free port unless `port` is given.

    The one who serves takes the socket as it is, so the port is never free between choosing it and serving on it.
    """
    listener = socket.socket()
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((LOOPBACK_HOST, port))
        listener.listen()
    except OSError:
        listener.close()
        raise
    return listener


def listener_port(listener: socket.socket) -> int:
    return int(listener.getsockname()[1])


def write_self_signed_certificate(directory: Path) -> tuple[Path, Path]:
    """A certificate for the loopback address, so the page is served over https like Skat's public origin."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, LOOPBACK_HOST)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address(LOOPBACK_HOST))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_file, certificate_file = directory / "key.pem", directory / "certificate.pem"
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    certificate_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return key_file, certificate_file


@dataclass(frozen=True)
class LoopbackSignIn:
    """The sign-in of a Skat on a free loopback port, its issuer a fake.

    `listener` is the port's socket, which the first start of Skat serves on.
    """

    host: str
    port: int
    listener: socket.socket
    sign_in: SignInSettings
    stores: SingleProcessStores
    issuer: FakeIssuer


def loopback_sign_in(
    directory: Path, host: str = LOOPBACK_HOST, **overrides: str | int | Path | None
) -> LoopbackSignIn:
    """Skat's sign-in on a free port; `host` is the name its public origin carries and it listens on loopback."""
    listener = listening_loopback_socket()
    port = listener_port(listener)
    sign_in = build_sign_in_settings(
        directory,
        **{
            "host": LOOPBACK_HOST,
            "port": port,
            "public_origin": f"https://{host}:{port}",
            "trusted_proxies": LOOPBACK_HOST,
            **overrides,
        },
    )
    return LoopbackSignIn(host, port, listener, sign_in, in_memory_stores(), FakeIssuer(sign_in))


class AlwaysTheSameDeal(random.Random):
    """A source that draws the same dealer and shuffles the same deck on every draw, whatever was drawn before."""

    def __init__(self, deal_seed: int) -> None:
        super().__init__()
        self._deal_seed = deal_seed

    def choice[Item](self, seq: SupportsLenAndGetItem[Item]) -> Item:
        self.seed(self._deal_seed)
        return super().choice(seq)

    def shuffle(self, x: MutableSequence[Any]) -> None:
        self.seed(self._deal_seed)
        super().shuffle(x)


class RunningServer:
    """Skat served over https on a loopback address, stopped and started the way `skat serve` does it.

    `stores` and `config` belong to the process now running; `restart` replaces them with a new process's.
    """

    def __init__(
        self,
        loopback: LoopbackSignIn,
        tls_directory: Path,
        engine: Engine,
        page_build_directory: Path,
        random_source: random.Random | None = None,
        heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
        unplayed_sweep_seconds: float = UNPLAYED_SWEEP_SECONDS,
        chair_clock: Callable[[], float] = time.monotonic,
        chair_scheduler: Scheduler | None = None,
    ) -> None:
        self.host = loopback.host
        self.base_url = f"https://{loopback.host}:{loopback.port}"
        self.issuer = loopback.issuer
        self.engine = engine
        self.stores = loopback.stores
        self._loopback = loopback
        self._listener: socket.socket | None = loopback.listener
        self._page_build_directory = page_build_directory
        self._random_source = random_source
        self._heartbeat_seconds = heartbeat_seconds
        self._unplayed_sweep_seconds = unplayed_sweep_seconds
        self._chair_clock = chair_clock
        self._chair_scheduler = chair_scheduler
        self._tls_files = write_self_signed_certificate(tls_directory)

    def start(self) -> None:
        app = create_app(
            self._loopback.sign_in.settings,
            page_build=PageBuild.load(self._page_build_directory),
            tables=TableService(PostgresTableTransactions(self.engine), random_source=self._random_source),
            rule_sets=RuleSetService(PostgresRuleSets(self.engine)),
            stores=self.stores,
            issuer_transports=self.issuer.transports,
            heartbeat_seconds=self._heartbeat_seconds,
            unplayed_sweep_seconds=self._unplayed_sweep_seconds,
            chair_clock=self._chair_clock,
            chair_scheduler=self._chair_scheduler,
        )
        self.config = installed_web_auth_config(app)
        key_file, certificate_file = self._tls_files
        self._server = streams_ending_server(
            app,
            **uvicorn_options(self._loopback.sign_in.settings),
            ssl_keyfile=str(key_file),
            ssl_certfile=str(certificate_file),
        )
        # A restart serves on the port again, and only the first start has the listener of the sign-in.
        listener = self._listener or listening_loopback_socket(self._loopback.sign_in.settings.port)
        self._listener = None
        self._thread = threading.Thread(target=self._server.run, args=([listener],), daemon=True)
        self._thread.start()
        deadline = time.monotonic() + READINESS_DEADLINE_SECONDS
        while not self._server.started:
            if not self._thread.is_alive():
                pytest.fail("Skat exited before it started")
            if time.monotonic() > deadline:
                pytest.fail(f"Skat did not start within {READINESS_DEADLINE_SECONDS} seconds")
            time.sleep(READINESS_POLL_INTERVAL_SECONDS)

    def stop(self, *, while_stopping: Callable[[], None] = lambda: None) -> None:
        """Signals the process to stop, runs `while_stopping`, and waits until the process has ended.

        Over https the process also waits for each browser to answer the close of its connection, which Skat's
        plain http behind the ingress does not, so how long the stop takes is not a property of Skat.
        """
        self._server.should_exit = True
        while_stopping()
        self._thread.join(timeout=SERVER_STOP_TIMEOUT_SECONDS)
        assert not self._thread.is_alive(), f"Skat did not stop within {SERVER_STOP_TIMEOUT_SECONDS} seconds"

    def restart(self, *, while_stopping: Callable[[], None]) -> None:
        """Stops Skat, then starts a new process on the same database, address and issuer.

        The new process starts with no session, as after an update. `while_stopping` runs as in `stop`.
        """
        self.stop(while_stopping=while_stopping)
        self.stores = in_memory_stores()
        self.start()


@contextmanager
def running_skat(
    loopback: LoopbackSignIn,
    tls_directory: Path,
    engine: Engine,
    page_build_directory: Path = BUILD_DIRECTORY,
    random_source: random.Random | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    unplayed_sweep_seconds: float = UNPLAYED_SWEEP_SECONDS,
    chair_clock: Callable[[], float] = time.monotonic,
    chair_scheduler: Scheduler | None = None,
) -> Iterator[RunningServer]:
    """Serve Skat over https on `loopback`.

    The page comes from `page_build_directory`, so a test can serve a copy it changes; `random_source` replaces the
    source the table service deals and draws the dealer from; `heartbeat_seconds` is the stream's idle tick;
    `unplayed_sweep_seconds` is how often the server looks for dealt tables nobody has played at for the days;
    `chair_clock` is the clock of the chair holds and of the waits at the table, which a test that lets a minute pass
    moves itself; `chair_scheduler` runs their timers and the pause before a next deal, which a test that checks a
    passed-in hand holds back, and is the event loop's timers when None.
    """
    server = RunningServer(
        loopback,
        tls_directory,
        engine,
        page_build_directory,
        random_source,
        heartbeat_seconds=heartbeat_seconds,
        unplayed_sweep_seconds=unplayed_sweep_seconds,
        chair_clock=chair_clock,
        chair_scheduler=chair_scheduler,
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()


def skat_on_new_database(
    directories: pytest.TempPathFactory,
    random_source: random.Random | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    unplayed_sweep_seconds: float = UNPLAYED_SWEEP_SECONDS,
    chair_clock: Callable[[], float] = time.monotonic,
    chair_scheduler: Scheduler | None = None,
    **settings_changes: float,
) -> AbstractContextManager[RunningServer]:
    """`skat_in_directory` over a directory of the session's temporary directories, for a fixture of a wider scope."""
    return skat_in_directory(
        directories.mktemp("server"),
        random_source,
        heartbeat_seconds,
        unplayed_sweep_seconds,
        chair_clock,
        chair_scheduler,
        **settings_changes,
    )


@contextmanager
def skat_in_directory(
    directory: Path,
    random_source: random.Random | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    unplayed_sweep_seconds: float = UNPLAYED_SWEEP_SECONDS,
    chair_clock: Callable[[], float] = time.monotonic,
    chair_scheduler: Scheduler | None = None,
    **settings_changes: float,
) -> Iterator[RunningServer]:
    """Skat on a free loopback port over a database of its own, its issuer a fake.

    `settings_changes` replace server settings, as a test that needs a short chair hold does; `random_source`
    replaces the source Skat deals from; `heartbeat_seconds` is the streams' idle tick, which a test that proves a
    wake sets so long that no heartbeat can stand in for it; `unplayed_sweep_seconds`, `chair_clock` and
    `chair_scheduler` are as in `running_skat`.
    """
    sign_in_directory = directory / "sign-in"
    tls_directory = directory / "tls"
    sign_in_directory.mkdir()
    tls_directory.mkdir()
    loopback = loopback_sign_in(sign_in_directory)
    settings = loopback.sign_in.settings.model_copy(update=settings_changes)
    loopback = replace(loopback, sign_in=replace(loopback.sign_in, settings=settings))
    with migrated_template() as template, created_database(template) as database_url:
        engine = create_store_engine(database_url)
        try:
            with running_skat(
                loopback,
                tls_directory,
                engine,
                random_source=random_source,
                heartbeat_seconds=heartbeat_seconds,
                unplayed_sweep_seconds=unplayed_sweep_seconds,
                chair_clock=chair_clock,
                chair_scheduler=chair_scheduler,
            ) as server:
                yield server
        finally:
            engine.dispose()
