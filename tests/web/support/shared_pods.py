"""Pods of one deployment in one test process: each its own app, all on one set of accounts, tables, place store and
stream leases, as the pods of Skat share one Postgres and one Redis.
"""

from contextlib import ExitStack, contextmanager

from tests.support.fake_tables import FakeTableStore
from tests.support.in_memory_agent_records import InMemoryAgentRecords
from tests.support.in_memory_leases import InMemoryLeases
from tests.support.in_memory_stores import in_memory_stores
from tests.web.support.changes import ControlledPlaceStore, RecordedChanges
from tests.web.support.skat import running_skat


class SharedBackends:
    """What the pods share; `pod_links` is the overrides of one pod's links."""

    def __init__(self):
        self.stores = in_memory_stores()
        self.tables = FakeTableStore()
        self.place_store = ControlledPlaceStore()
        self.leases = InMemoryLeases()
        self.records = InMemoryAgentRecords()

    def pod_links(self):
        return {"place_store": self.place_store, "stream_leases": self.leases, "agent_records": self.records}


@contextmanager
def running_pods(count, hold, issuer, time):
    """`count` running apps over one `SharedBackends`; each app's `changes` tells through the shared place store."""
    shared = SharedBackends()
    with ExitStack() as running:
        pods = []
        for _ in range(count):
            changes = RecordedChanges(shared.place_store)
            pod = running.enter_context(
                _one_pod(shared, changes, hold, issuer, time),
            )
            pod.changes = changes
            pod.shared = shared
            pods.append(pod)
        yield pods


@contextmanager
def _one_pod(shared, changes, hold, issuer, time):
    yield from running_skat(
        hold,
        issuer,
        time,
        store=shared.tables,
        stores=shared.stores,
        pod=shared.pod_links(),
        resource_changes=changes.wired,
    )
