"""The changes an app tells its listening agents, recorded, and wired to the app's own roster."""

from agents.mcp_server import ResourceChanges


class RecordedChanges(ResourceChanges):
    """The changes the app tells, as (account, uri) in the order told; set `failure` and each one raises it.

    It is the factory an app takes: `wired` hands it the app's listening callback, which it forwards, so the app's
    roster runs as in production. Wired again, as by a restart, it forwards to the new app.
    """

    def __init__(self):
        super().__init__(self._forward)
        self.told = []
        self.failure = None
        self._callback = None

    def wired(self, listening_changed):
        self._callback = listening_changed
        return self

    def _forward(self, principal, uri, listens):
        if self._callback is not None:
            self._callback(principal, uri, listens)

    def changed(self, recipient, uri):
        self.told.append((recipient.sub, uri))
        if self.failure is not None:
            raise self.failure
        super().changed(recipient, uri)
