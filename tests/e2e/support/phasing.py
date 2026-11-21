import os
import time
import warnings

laps: list[tuple[str, float]] = []
sums: dict[str, float] = {}
started = [time.monotonic()]


def begin() -> None:
    laps.clear()
    sums.clear()
    started[0] = time.monotonic()
    laps.append(("load0", os.getloadavg()[0]))


def lap(label: str) -> None:
    now = time.monotonic()
    laps.append((label, now - started[0]))
    started[0] = now


def add(label: str, seconds: float) -> None:
    sums[label] = sums.get(label, 0.0) + seconds


def report(case: str) -> None:
    laps.append(("load1", os.getloadavg()[0]))
    text = " ".join(f"{label}={value:.1f}" for label, value in [*laps, *sums.items()])
    warnings.warn(f"PHASES {case} worker={os.environ.get("PYTEST_XDIST_WORKER")} cpus={os.cpu_count()} {text}", stacklevel=1)
