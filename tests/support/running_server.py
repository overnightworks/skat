import threading
import time
from typing import TYPE_CHECKING

from skat.host.main import streams_ending_server, uvicorn_options

if TYPE_CHECKING:
    from fastapi import FastAPI
    from uvicorn import Server

    from skat.web.settings import ServerSettings

STARTED_WITHIN_SECONDS = 10
POLL_SECONDS = 0.05


def started_server(app: FastAPI, settings: ServerSettings) -> tuple[Server, threading.Thread]:
    """Skat's server on a thread of this process, serving `app` once it has started; the caller ends it with
    `should_exit` and joins the thread.
    """
    server = streams_ending_server(app, **uvicorn_options(settings))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + STARTED_WITHIN_SECONDS
    while not server.started and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    return server, thread
