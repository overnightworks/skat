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
    import random
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from sqlalchemy import Engine
    from webauth.single_process_stores import SingleProcessStores

    from tests.support.sign_in_settings import SignInSettings

LOOPBACK_HOST = "127.0.0.1"

READINESS_POLL_INTERVAL_SECONDS = 0.1
READINESS_DEADLINE_SECONDS = 20
SERVER_STOP_TIMEOUT_SECONDS = 10


def reserve_free_port() -> int:
    with socket.socket() as probe:
        probe.bind((LOOPBACK_HOST, 0))
        return int(probe.getsockname()[1])


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
    """The sign-in of a Skat on a free loopback port, its issuer a fake."""

    host: str
    port: int
    sign_in: SignInSettings
    stores: SingleProcessStores
    issuer: FakeIssuer


def loopback_sign_in(
    directory: Path, host: str = LOOPBACK_HOST, **overrides: str | int | Path | None
) -> LoopbackSignIn:
    """Skat's sign-in on a free port; `host` is the name its public origin carries and it listens on loopback."""
    port = reserve_free_port()
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
    return LoopbackSignIn(host, port, sign_in, in_memory_stores(), FakeIssuer(sign_in))


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
    ) -> None:
        self.host = loopback.host
        self.base_url = f"https://{loopback.host}:{loopback.port}"
        self.issuer = loopback.issuer
        self.engine = engine
        self.stores = loopback.stores
        self._loopback = loopback
        self._page_build_directory = page_build_directory
        self._random_source = random_source
        self._heartbeat_seconds = heartbeat_seconds
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
) -> Iterator[RunningServer]:
    """Serve Skat over https on `loopback`.

    The page comes from `page_build_directory`, so a test can serve a copy it changes; `random_source` replaces the
    source the table service deals and draws the dealer from; `heartbeat_seconds` is the stream's idle tick.
    """
    server = RunningServer(
        loopback, tls_directory, engine, page_build_directory, random_source, heartbeat_seconds=heartbeat_seconds
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()


@contextmanager
def skat_on_new_database(
    directories: pytest.TempPathFactory,
    random_source: random.Random | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    **settings_changes: float,
) -> Iterator[RunningServer]:
    """Skat on a free loopback port over a database of its own, its issuer a fake.

    `settings_changes` replace server settings, as a test that needs a short chair hold does; `random_source`
    replaces the source Skat deals from; `heartbeat_seconds` is the streams' idle tick, which a test that proves a
    wake sets so long that no heartbeat can stand in for it.
    """
    loopback = loopback_sign_in(directories.mktemp("sign-in"))
    settings = loopback.sign_in.settings.model_copy(update=settings_changes)
    loopback = replace(loopback, sign_in=replace(loopback.sign_in, settings=settings))
    with migrated_template() as template, created_database(template) as database_url:
        engine = create_store_engine(database_url)
        try:
            with running_skat(
                loopback,
                directories.mktemp("tls"),
                engine,
                random_source=random_source,
                heartbeat_seconds=heartbeat_seconds,
            ) as server:
                yield server
        finally:
            engine.dispose()
