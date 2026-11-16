"""The changes an app tells its listening agents, recorded, and wired to the app's own roster."""

from agents.mcp_server import ResourceChanges

from tests.support.in_memory_place_store import InMemoryPlaceStore


class RecordedChanges(ResourceChanges):
    """The changes the app tells, as (account, uri) in the order told; set `failure` and each one raises it.

    It is the factory an app takes: `wired` hands it the app's roster, whose callbacks it forwards, so the app's
    roster runs as in production. Wired again, as by a restart, it forwards to the new app. The store it tells
    through is its own, in `store`, whatever store the app offers.
    """

    def __init__(self, store=None):
        self.store = InMemoryPlaceStore() if store is None else store
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
