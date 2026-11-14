import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx2

from skat.web.constants import HEALTH_PATH
from tests.support.page_build import FIXTURE_DIRECTORY
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import IO

REPOSITORY = Path(__file__).parents[2]
LOOPBACK = "127.0.0.1"
START_DEADLINE_SECONDS = 60
STOP_DEADLINE_SECONDS = 30
POLL_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 10
# What `skat serve` runs, on the tests' page build instead of the frontend's.
SERVE = (
    "import sys; from pathlib import Path; from skat.host.main import main; "
    "main(['serve'], build_directory=Path(sys.argv[1]))"
)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((LOOPBACK, 0))
        return int(probe.getsockname()[1])


class SkatProcess:
    """One `skat serve` process on a loopback port, reached with the Host header of Skat's public origin.

    Its settings come from `environment`; `start` waits until the process answers its readiness probe and `stop`
    ends it with SIGTERM, as an orchestrator does.
    """

    def __init__(self, environment: Mapping[str, str], log: Path) -> None:
        self.port = free_port()
        self._environment = {
            "PATH": os.environ["PATH"],
            "PYTHONPATH": str(REPOSITORY / "src"),
            **environment,
            "SKAT_HOST": LOOPBACK,
            "SKAT_PORT": str(self.port),
        }
        self._log_path = log
        self._log: IO[bytes] | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self._log = self._log_path.open("ab")
        self._process = subprocess.Popen(  # noqa: S603 - the interpreter and the fixed program text are the test's own
            [sys.executable, "-c", SERVE, str(FIXTURE_DIRECTORY)],
            env=self._environment,
            cwd=REPOSITORY,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + START_DEADLINE_SECONDS
        while not self._answers_readiness():
            assert self._process.poll() is None, f"skat serve exited early:\n{self.output()}"
            assert time.monotonic() < deadline, f"skat serve was not ready in time:\n{self.output()}"
            time.sleep(POLL_SECONDS)

    def stop(self) -> int:
        """Sends SIGTERM and returns the exit status once the process has ended."""
        assert self._process is not None
        self._process.send_signal(signal.SIGTERM)
        status = self._process.wait(timeout=STOP_DEADLINE_SECONDS)
        self._close_log()
        return status

    def kill(self) -> None:
        """Ends the process at once, for a test's teardown; a process that has ended is left as it is."""
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            self._process.wait()
        self._close_log()

    def request(self, method: str, path: str, **headers: str) -> httpx2.Response:
        return httpx2.request(
            method,
            f"http://{LOOPBACK}:{self.port}{path}",
            headers={"host": TEST_PUBLIC_ORIGIN.removeprefix("https://"), **headers},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    def output(self) -> str:
        return self._log_path.read_text(errors="replace")

    def _answers_readiness(self) -> bool:
        try:
            return self.request("GET", HEALTH_PATH).status_code == httpx2.codes.OK
        except httpx2.TransportError:
            return False

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None
