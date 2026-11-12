"""An agent that listens on Skat's standing as a runner does: the SDK's client over streamable HTTP against the
running server, on an event loop of its own thread, so the browser keeps its owning thread. A wake carries no data
and a listen has no replay, so the agent reads its standing after every wake and after every listen it opens again.
"""

import asyncio
import json
import threading
import time
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

import httpx2
from agents.member import ACCEPT_INVITATION_TOOL, STANDING_URI
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.subscriptions import SubscriptionLost

if TYPE_CHECKING:
    from tests.e2e.support.server import RunningServer

REQUEST_SECONDS = 30


class ListeningAgent:
    """The agent `name` of the person whose account is `owner_account`, with an account and a token of its own. It
    listens on its standing from its start until `close`, which ends the stream and joins the thread; close it before
    the server stops.
    """

    def __init__(self, server: RunningServer, owner_account: str, name: str, subject: str) -> None:
        self._url = f"{server.base_url}/mcp"
        self._token = server.issuer.agent_token(subject, agent_owner=owner_account, agent_name=name)
        self._loop = asyncio.new_event_loop()
        self._opened = threading.Event()
        self._acknowledged = threading.Event()
        self._woken = threading.Event()
        self._stopping = asyncio.Event()
        self._client: Client
        self._stream: asyncio.Task[None] | None = None
        self._thread = threading.Thread(target=self._loop.run_until_complete, args=(self._hold_the_client(),))
        self._thread.start()
        if not self._opened.wait(REQUEST_SECONDS):
            self.close()
            message = "the SDK client did not open"
            raise TimeoutError(message)
        self._stream = self._run(self._start_listening())
        assert self._acknowledged.wait(REQUEST_SECONDS), "the server never acknowledged the listen"

    async def _hold_the_client(self) -> None:
        http = httpx2.AsyncClient(
            headers={"authorization": f"Bearer {self._token}"},
            timeout=httpx2.Timeout(REQUEST_SECONDS, read=None),
            verify=False,  # the loopback certificate is self-signed
            trust_env=False,
        )
        async with AsyncExitStack() as held:
            async with asyncio.timeout(REQUEST_SECONDS):
                await held.enter_async_context(http)
                self._client = await held.enter_async_context(
                    Client(streamable_http_client(self._url, http_client=http))
                )
            self._opened.set()
            await self._stopping.wait()

    async def _listen_for_wakes(self) -> None:
        """Listens again whenever the stream ended, because the server bounds a stream and may end it; the standing
        is read after each listen, since a change before it left no wake behind.
        """
        while True:
            try:
                async with self._client.listen(resource_subscriptions=[STANDING_URI]) as stream:
                    self._acknowledged.set()
                    self._woken.set()
                    async for _event in stream:
                        self._woken.set()
            except SubscriptionLost:
                continue

    async def _start_listening(self) -> asyncio.Task[None]:
        return asyncio.create_task(self._listen_for_wakes())

    def _run(self, coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(REQUEST_SECONDS)

    def invitation_within(self, seconds: float) -> dict[str, Any]:
        """The standing that holds the invitation: the agent reads its standing at each wake until one does."""
        deadline = time.monotonic() + seconds
        while self._woken.wait(max(0.0, deadline - time.monotonic())):
            self._woken.clear()
            standings = json.loads(self._run(self._client.read_resource(STANDING_URI)).contents[0].text)["standings"]
            if invited := [standing for standing in standings if standing["state"] == "invited"]:
                return invited[0]
        message = "no wake of the stream brought an invitation"
        raise AssertionError(message)

    def accept(self, standing: dict[str, Any]) -> dict[str, Any]:
        invitation = standing["invitation"]
        arguments = {"place": standing["place"], "invitation": invitation["id"], "epoch": invitation["epoch"]}
        result = self._run(self._client.call_tool(ACCEPT_INVITATION_TOOL, arguments))
        text = result.content[0].text
        assert not result.is_error, text
        return json.loads(text)

    def close(self) -> None:
        if self._stream is not None:
            self._loop.call_soon_threadsafe(self._stream.cancel)
        self._loop.call_soon_threadsafe(self._stopping.set)
        self._thread.join(REQUEST_SECONDS)
        self._loop.close()
