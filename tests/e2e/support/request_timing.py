"""Temporary measurement of where a request's time goes between the browser and the app (item 712)."""

import asyncio
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

DIRECTORY_VARIABLE = "SKAT_E2E_TIMING_DIR"


def enabled() -> bool:
    return bool(os.environ.get(DIRECTORY_VARIABLE))


def record(kind: str, **fields: Any) -> None:
    directory = Path(os.environ[DIRECTORY_VARIABLE])
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{os.getpid()}.jsonl").open("a") as out:
        out.write(json.dumps({"kind": kind, "pid": os.getpid(), **fields}) + "\n")


def watch_for_stalls(state: dict[str, Any]) -> None:
    """Names what every thread runs while the server's loop has not ticked for 300 ms."""
    loop_clock = time.pthread_getcpuclockid(state["thread"])
    reported_beat = None
    while True:
        time.sleep(0.05)
        beat = state["beat"]
        if time.perf_counter() - beat < 0.3 or beat == reported_beat:
            continue
        reported_beat = beat
        stacks = {
            ("loop" if thread_id == state["thread"] else "main" if thread_id == threading.main_thread().ident else str(thread_id)): [
                f"{entry.name}:{entry.filename.rsplit('/', 1)[-1]}:{entry.lineno}" for entry in traceback.extract_stack(frame)[-5:]
            ]
            for thread_id, frame in sys._current_frames().items()  # noqa: SLF001
        }
        record(
            "stall",
            at=time.time(),
            stale_ms=round((time.perf_counter() - beat) * 1000),
            loop_cpu_ms_since_beat=round((time.clock_gettime(loop_clock) - state["beat_cpu"]) * 1000),
            load=os.getloadavg(),
            stacks=stacks,
        )


def timed_app(app: Any) -> Any:
    state: dict[str, Any] = {"sampler": None}

    async def sample_loop_lag() -> None:
        while True:
            before = time.perf_counter()
            state["beat"] = before
            state["beat_cpu"] = time.clock_gettime(time.pthread_getcpuclockid(state["thread"]))
            await asyncio.sleep(0.02)
            lag = time.perf_counter() - before - 0.02
            if lag > 0.05:
                record("loop_lag", at=time.time(), lag_ms=round(lag * 1000))

    async def wrapper(scope: Any, receive: Any, send: Any) -> None:
        if state["sampler"] is None:
            state["thread"] = threading.get_ident()
            state["beat"] = time.perf_counter()
            state["beat_cpu"] = 0.0
            threading.Thread(target=watch_for_stalls, args=(state,), daemon=True).start()
            state["sampler"] = asyncio.get_running_loop().create_task(sample_loop_lag())
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        entry = time.time()
        target = scope["path"] + (f"?{scope['query_string'].decode()}" if scope["query_string"] else "")

        async def noting_send(message: Any) -> None:
            if message["type"] == "http.response.start":
                record("app", target=target, method=scope["method"], entry=entry, start=time.time())
            await send(message)

        await app(scope, receive, noting_send)

    return wrapper


def note_browser_request(request: Any) -> None:
    timing = request.timing
    record(
        "browser",
        url=request.url,
        method=request.method,
        resource=request.resource_type,
        sent=timing["startTime"] + max(timing["requestStart"], 0),
        first_byte=timing["startTime"] + timing["responseStart"],
        done=timing["startTime"] + timing["responseEnd"],
    )
