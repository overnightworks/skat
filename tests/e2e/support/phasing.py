import os
import time
import warnings

laps: list[tuple[str, float]] = []
started = [time.monotonic()]


def begin() -> None:
    laps.clear()
    started[0] = time.monotonic()
    laps.append(("load0", os.getloadavg()[0]))


def lap(label: str) -> None:
    now = time.monotonic()
    laps.append((label, now - started[0]))
    started[0] = now


def report(case: str) -> None:
    laps.append(("load1", os.getloadavg()[0]))
    text = " ".join(f"{label}={value:.1f}" for label, value in laps)
    warnings.warn(f"PHASES {case} worker={os.environ.get('PYTEST_XDIST_WORKER')} {text}", stacklevel=1)
