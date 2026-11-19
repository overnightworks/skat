"""The changes an app tells its listening agents, recorded, and a place store a test controls."""

from agents.mcp_server import InMemoryPlaceStore, PlaceStoreError, ResourceChanges


class ControlledPlaceStore(InMemoryPlaceStore):
    """The library's in-memory place store with the controls its tests of the host need and the library lacks: a store
    that does not answer, and one that lists no listener although it records the streams.
    """

    def __init__(self):
        super().__init__()
        self.unreachable = False
        self.lists_no_listener = False

    async def listeners(self, uri):
        if self.unreachable:
            raise PlaceStoreError("the store does not answer")
        return frozenset() if self.lists_no_listener else await super().listeners(uri)


class RecordedChanges(ResourceChanges):
    """The changes the app tells, as (account, uri) in the order told; set `failure` and each one raises it.

    It is the factory an app takes: `wired` hands the app these changes. The store it tells through is its own, in
    `store`, whatever store the app offers; pods of one test share it by passing it in.
    """

    def __init__(self, store=None):
        self.store = ControlledPlaceStore() if store is None else store
        super().__init__(self.store)
        self.told = []
        self.failure = None

    def wired(self, _store):
        return self

    async def changed(self, recipient, uri):
        self.told.append((recipient.sub, uri))
        if self.failure is not None:
            raise self.failure
        await super().changed(recipient, uri)
