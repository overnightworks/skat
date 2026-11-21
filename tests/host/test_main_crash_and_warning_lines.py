import json
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

CRASH_ENTRY = ["-m", "skat.host.main", "migrate"]
WARNING_ENTRY = [
    "-c",
    "import warnings, skat.host.main as host; "
    "host._run = lambda *_: warnings.warn('hidden detail', UserWarning); "
    "host.main(['migrate'])",
]


def run_host(entry: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, list[dict]]:
    for name in ("DATABASE_URL", "SKAT_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    finished = subprocess.run(  # noqa: S603 - the interpreter running the tests, with fixed arguments
        [sys.executable, "-I", *entry], capture_output=True, text=True, check=False, timeout=120
    )
    output = finished.stdout + finished.stderr
    return finished.returncode, [json.loads(line) for line in output.splitlines() if line.strip()]


class TestHostLogsCrashesAndWarningsAsJsonLines:
    def test_an_uncaught_failure_is_one_critical_line_and_the_process_exits_non_zero(self, monkeypatch):
        exit_code, lines = run_host(CRASH_ENTRY, monkeypatch)

        crashes = [line for line in lines if line["event"] == "process.crashed"]
        assert exit_code != 0
        assert len(crashes) == 1
        assert crashes[0]["level"] == "critical"
        assert crashes[0]["service"] == "skat"
        assert "Traceback" in crashes[0]["exception"]

    def test_a_python_warning_is_one_warning_line_without_its_message(self, monkeypatch):
        exit_code, lines = run_host(WARNING_ENTRY, monkeypatch)

        warnings_logged = [line for line in lines if line["event"] == "python_warning.raised"]
        assert exit_code == 0
        assert len(warnings_logged) == 1
        assert warnings_logged[0]["level"] == "warning"
        assert warnings_logged[0]["error_type"] == "UserWarning"
        assert "hidden detail" not in json.dumps(warnings_logged[0])
