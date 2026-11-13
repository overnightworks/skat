import anyio
import httpx2

from tests.web.support.sdk_agent import InProcessApp


def test_an_app_that_writes_after_the_client_closed_its_response_ends_without_error():
    written_after_close = anyio.Event()

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await receive()
        await send({"type": "http.response.body", "body": b"second", "more_body": True})
        written_after_close.set()

    async def scenario():
        async with anyio.create_task_group() as tasks:
            transport = InProcessApp(app, tasks)
            response = await transport.handle_async_request(httpx2.Request("GET", "https://skat.example/stream"))
            await response.aclose()
            await written_after_close.wait()

    anyio.run(scenario)
