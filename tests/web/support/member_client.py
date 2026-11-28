"""The agents library's member client against the app in this process.

The member session is asynchronous and its listen is an open stream, so it runs on the event loop the app's lifespan
runs on, reached through the test client's portal; the test body stays synchronous. A person's move in the body reaches
the app through the test client as everywhere else in the web tests.
"""

from contextlib import asynccontextmanager, contextmanager, suppress

import anyio
import httpx2
from agents.mcp_client import ResourceWake, open_member_session
from agents.mcp_wire import MCP_ENDPOINT_PATH
from agents.member import PlaceRef
from pydantic import SecretStr

from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import SUBJECT, ToolAnswer, view_uri_of, window_uri_of

EVENT_WITHIN_SECONDS = 10
TOOLS_CHANGED = "tools-changed"


class _Streamed(httpx2.AsyncByteStream):
    def __init__(self, chunks, disconnected):
        self._chunks = chunks
        self._disconnected = disconnected

    async def __aiter__(self):
        async for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        self._disconnected.set()
        await self._chunks.aclose()


class InProcessApp(httpx2.AsyncBaseTransport):
    """Carries a client's requests to an ASGI app on the running loop and hands each response back as the app writes
    it, so an open stream delivers while it is open.
    """

    def __init__(self, app, tasks):
        self._app = app
        self._tasks = tasks

    async def handle_async_request(self, request):
        body = await request.aread()
        url = request.url
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "scheme": url.scheme,
            "path": url.path,
            "raw_path": url.raw_path.split(b"?")[0],
            "query_string": url.query,
            "root_path": "",
            "headers": [(name.lower(), value) for name, value in request.headers.raw],
            "server": (url.host, url.port or 443),
            "client": ("sdk-client", 50000),
        }
        chunks_in, chunks_out = anyio.create_memory_object_stream[bytes](max_buffer_size=1024)
        answered = anyio.Event()
        disconnected = anyio.Event()
        start = {}
        requested = False

        async def receive():
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                start.update(status=message["status"], headers=message["headers"])
                answered.set()
            elif message["type"] == "http.response.body":
                if message.get("body"):
                    # A client that closed its response no longer reads; a real server drops what the app still writes.
                    with suppress(anyio.BrokenResourceError):
                        await chunks_in.send(message["body"])
                if not message.get("more_body", False):
                    chunks_in.close()

        async def run():
            try:
                await self._app(scope, receive, send)
            finally:
                chunks_in.close()
                answered.set()

        self._tasks.start_soon(run)
        await answered.wait()
        return httpx2.Response(start["status"], headers=start["headers"], stream=_Streamed(chunks_out, disconnected))


class MemberClient:
    """The agent through the agents library's `MemberSession`: its own token at every request, tools called, places read
    and the standing listened to like a runner does. Its methods are synchronous; the session runs on the app's loop.
    """

    def __init__(self, skat, issuer, subject=SUBJECT, **claims):
        self._skat = skat
        self._token = issuer.agent_token(subject, **claims)

    @asynccontextmanager
    async def _connected(self):
        async with anyio.create_task_group() as tasks:
            transport = InProcessApp(self._skat.app, tasks)
            url = TEST_PUBLIC_ORIGIN + MCP_ENDPOINT_PATH
            async with open_member_session(url, lambda: SecretStr(self._token), transport=transport) as session:
                yield session
            tasks.cancel_scope.cancel()

    @contextmanager
    def connected(self):
        """A member session; leaving it ends its streams."""
        portal = self._skat.client.portal
        with portal.wrap_async_context_manager(self._connected()) as session:
            yield MemberCalls(portal, session)


class MemberCalls:
    def __init__(self, portal, session):
        self._portal = portal
        self._session = session

    def call(self, tool, **arguments):
        outcome = self._portal.call(self._session.invoke, tool, arguments)
        return ToolAnswer(outcome.is_error, outcome.content)

    def view(self, table_id):
        """The table's view as the app serves it: revision, awaits_you, state and traceparent."""
        view = self._portal.call(self._session.read_view, PlaceRef(kind="table", id=table_id))
        assert view is not None, f"the app shows this member no view of table {table_id}"
        return view.model_dump(mode="json")

    @contextmanager
    def listening(self, *, tools_list_changed=False):
        """A listen stream on the agent's standing, which delivers the views it lists too, and the change of the tool
        list when asked.
        """
        with self._portal.wrap_async_context_manager(self._session.listen()) as wakes:
            yield MemberEvents(self, self._portal, wakes, tools_list_changed)


class MemberEvents:
    def __init__(self, calls, portal, wakes, tools_list_changed):
        self._calls = calls
        self._portal = portal
        self._wakes = wakes
        self._tools_list_changed = tools_list_changed

    def next_uri(self):
        """The URI the next change of the stream names."""
        kind = self.next_kind()
        assert kind != TOOLS_CHANGED
        return kind

    def next_kind(self):
        """What the next event of the stream is: `TOOLS_CHANGED` for the notice that the tool list changed, else the
        URI that changed.
        """

        async def next_wake():
            with anyio.fail_after(EVENT_WITHIN_SECONDS):
                async for wake in self._wakes:
                    if isinstance(wake, ResourceWake):
                        return wake.uri
                    if self._tools_list_changed:
                        return TOOLS_CHANGED
            raise AssertionError("the stream ended")

        return self._portal.call(next_wake)

    def woken_view(self, table_id):
        """Waits for the pulse of the table's view, which a commit tells after the pulse of its window, and reads the
        view after it.
        """
        uri = self.next_uri()
        if uri == window_uri_of(table_id):
            uri = self.next_uri()
        assert uri == view_uri_of(table_id)
        return self._calls.view(table_id)
