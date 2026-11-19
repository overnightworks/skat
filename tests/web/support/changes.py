"""The changes an app tells its listening agents, recorded, and wired to the app's own roster."""

import asyncio

from agents.mcp_server import InMemoryPlaceStore, PlaceStoreError, ResourceChanges

# A resync that reads nothing fails its test instead of hanging it.
READ_WITHIN_SECONDS = 5


class ControlledPlaceStore(InMemoryPlaceStore):
    """The library's in-memory place store with the controls its tests of the host need and the library lacks: a turn
    put on the followers as another pod's would arrive, a record that tells no turn, and a store that does not answer.
    """

    def __init__(self):
        super().__init__()
        self.unreachable = False
        self._turns_told = True
        self._listeners_read = asyncio.Event()

    def _broadcast(self, event):
        if self._turns_told:
            super()._broadcast(event)

    async def inject(self, event):
        """Puts the event on every follower and returns once they have handled it."""
        super()._broadcast(event)
        await self._settled()

    async def record_without_turn(self, stream, principal, uris, holds_for):
        """Another pod recorded the stream while this pod's subscription was down: no follower is told."""
        self._turns_told = False
        try:
            await self.acknowledged(stream, principal, uris, holds_for)
        finally:
            self._turns_told = True

    async def resubscribed(self):
        """The subscription is confirmed again; returns once a read of `listeners` that it caused has answered."""
        self._listeners_read.clear()
        self.resubscribe()
        async with asyncio.timeout(READ_WITHIN_SECONDS):
            await self._listeners_read.wait()

    async def listeners(self, uri):
        try:
            if self.unreachable:
                raise PlaceStoreError("the store does not answer")
            return await super().listeners(uri)
        finally:
            self._listeners_read.set()

    async def listens_to(self, principal, uri):
        if self.unreachable:
            raise PlaceStoreError("the store does not answer")
        return await super().listens_to(principal, uri)

    async def _settled(self):
        # A follower pops its inbox and handles the event without yielding, so an empty inbox means handled.
        while any(not follower.inbox.empty() for follower in self._followers):  # noqa: ASYNC110 the library's inbox offers nothing to wait on
            await asyncio.sleep(0)


class RecordedChanges(ResourceChanges):
    """The changes the app tells, as (account, uri) in the order told; set `failure` and each one raises it.

    It is the factory an app takes: `wired` hands it the app's roster, whose callbacks it forwards, so the app's
    roster runs as in production. Wired again, as by a restart, it forwards to the new app. The store it tells
    through is its own, in `store`, whatever store the app offers.
    """

    def __init__(self, store=None):
        self.store = ControlledPlaceStore() if store is None else store
        super().__init__(self.store, listening_changed=self._forward_change, listening_resynced=self._forward_resync)
        self.told = []
        self.failure = None
        self._roster = None

    def wired(self, _store, roster):
        self._roster = roster
        return self

    def _forward_change(self, principal, uri, listens):
        if self._roster is not None:
            self._roster.listening_changed(principal, uri, listens)

    def _forward_resync(self):
        if self._roster is not None:
            self._roster.listening_resynced()

    async def changed(self, recipient, uri):
        self.told.append((recipient.sub, uri))
        if self.failure is not None:
            raise self.failure
        await super().changed(recipient, uri)
