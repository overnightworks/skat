"""The in-process transport of the SDK agent: an app writing to a client that has gone away is not an error."""

import asyncio

import anyio
import httpx2

from tests.web.support.sdk_agent import InProcessApp


def test_an_app_that_writes_after_the_client_closed_its_stream_ends_without_an_error():
    wrote_late = asyncio.Event()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await receive()
        await receive()
        await send({"type": "http.response.body", "body": b"late", "more_body": False})
        wrote_late.set()

    async def drive():
        async with anyio.create_task_group() as tasks:
            transport = InProcessApp(app, tasks)
            response = await transport.handle_async_request(httpx2.Request("GET", "http://test/stream"))
            await response.stream.aclose()
            await asyncio.wait_for(wrote_late.wait(), timeout=10)

    asyncio.run(drive())
