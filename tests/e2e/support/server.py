import datetime
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from ipaddress import IPv4Address
from typing import TYPE_CHECKING

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.host.main import streams_ending_server, uvicorn_options
from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.service import TableService
from skat.web.page_build import BUILD_DIRECTORY, PageBuild
from skat.web.stores import SignInStores
from tests.support.fake_issuer import FakeIssuer
from tests.support.postgres import created_database, migrated_template
from tests.support.sign_in_settings import build_sign_in_settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from sqlalchemy import Engine

    from tests.support.sign_in_settings import SignInSettings

LOOPBACK_HOST = "127.0.0.1"

READINESS_POLL_INTERVAL_SECONDS = 0.1
READINESS_DEADLINE_SECONDS = 20
SERVER_STOP_TIMEOUT_SECONDS = 10


def _reserve_free_port() -> int:
    with socket.socket() as probe:
        probe.bind((LOOPBACK_HOST, 0))
        return int(probe.getsockname()[1])


def _write_self_signed_certificate(directory: Path) -> tuple[Path, Path]:
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
    """The sign-in of a Skat on a free loopback port, its issuer a fake."""

    port: int
    sign_in: SignInSettings
    stores: SignInStores
    issuer: FakeIssuer


def loopback_sign_in(directory: Path) -> LoopbackSignIn:
    port = _reserve_free_port()
    sign_in = build_sign_in_settings(
        directory,
        host=LOOPBACK_HOST,
        port=port,
        public_origin=f"https://{LOOPBACK_HOST}:{port}",
        trusted_proxies=LOOPBACK_HOST,
    )
    return LoopbackSignIn(port, sign_in, SignInStores.in_memory(), FakeIssuer(sign_in))


class RunningServer:
    """Skat served over https on a loopback address, stopped and started the way `skat serve` does it.

    `stores` and `config` belong to the process now running; `restart` replaces them with a new process's.
    """

    def __init__(
        self, loopback: LoopbackSignIn, tls_directory: Path, engine: Engine, page_build_directory: Path
    ) -> None:
        self.base_url = f"https://{LOOPBACK_HOST}:{loopback.port}"
        self.issuer = loopback.issuer
        self.engine = engine
        self.stores = loopback.stores
        self._loopback = loopback
        self._page_build_directory = page_build_directory
        self._tls_files = _write_self_signed_certificate(tls_directory)

    def start(self) -> None:
        app = create_app(
            self._loopback.sign_in.settings,
            page_build=PageBuild.load(self._page_build_directory),
            tables=TableService(PostgresTableTransactions(self.engine)),
            stores=self.stores,
            issuer_transports=self.issuer.transports,
        )
        self.config = installed_web_auth_config(app)
        key_file, certificate_file = self._tls_files
        self._server = streams_ending_server(
            app,
            **uvicorn_options(self._loopback.sign_in.settings),
            ssl_keyfile=str(key_file),
            ssl_certfile=str(certificate_file),
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + READINESS_DEADLINE_SECONDS
        while not self._server.started:
            if not self._thread.is_alive():
                pytest.fail("Skat exited before it started")
            if time.monotonic() > deadline:
                pytest.fail(f"Skat did not start within {READINESS_DEADLINE_SECONDS} seconds")
            time.sleep(READINESS_POLL_INTERVAL_SECONDS)

    def stop(self) -> float:
        """Stops the process and returns the seconds the stop took."""
        stopping = time.monotonic()
        self._server.should_exit = True
        self._thread.join(timeout=SERVER_STOP_TIMEOUT_SECONDS)
        assert not self._thread.is_alive(), f"Skat did not stop within {SERVER_STOP_TIMEOUT_SECONDS} seconds"
        return time.monotonic() - stopping

    def restart(self, *, while_stopped: Callable[[], None]) -> float:
        """Stops Skat, runs `while_stopped`, and starts a new process on the same database, address and issuer.

        The new process starts with no session, as after an update. Returns the seconds the stop took.
        """
        stop_seconds = self.stop()
        while_stopped()
        self.stores = SignInStores.in_memory()
        self.start()
        return stop_seconds


@contextmanager
def running_skat(
    loopback: LoopbackSignIn,
    tls_directory: Path,
    engine: Engine,
    page_build_directory: Path = BUILD_DIRECTORY,
) -> Iterator[RunningServer]:
    """Serve Skat over https on `loopback`.

    The page comes from `page_build_directory`, so a test can serve a copy it changes.
    """
    server = RunningServer(loopback, tls_directory, engine, page_build_directory)
    server.start()
    try:
        yield server
    finally:
        server.stop()


@contextmanager
def skat_on_new_database(directories: pytest.TempPathFactory, **settings_changes: float) -> Iterator[RunningServer]:
    """Skat on a free loopback port over a database of its own, its issuer a fake.

    `settings_changes` replace server settings, as a test that needs a short chair hold does.
    """
    loopback = loopback_sign_in(directories.mktemp("sign-in"))
    settings = loopback.sign_in.settings.model_copy(update=settings_changes)
    loopback = replace(loopback, sign_in=replace(loopback.sign_in, settings=settings))
    with migrated_template() as template, created_database(template) as database_url:
        engine = create_store_engine(database_url)
        try:
            with running_skat(loopback, directories.mktemp("tls"), engine) as server:
                yield server
        finally:
            engine.dispose()
