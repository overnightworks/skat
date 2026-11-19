from dataclasses import replace
from typing import TYPE_CHECKING

from agents.mcp_server import InMemoryPlaceStore
from tandem.testing import FakeWakeBus
from webauth.rate_limit import SingleProcessRateLimitBackend
from webauth.single_process_stores import SingleProcessStores

from skat.host.app import PodLinks
from skat.web.sign_in import LoggingAuditSink
from tests.support.in_memory_leases import InMemoryLeases

if TYPE_CHECKING:
    from webauth.ports import AuditSink


def in_memory_stores(audit: AuditSink | None = None) -> SingleProcessStores:
    return SingleProcessStores(audit=LoggingAuditSink() if audit is None else audit)


def in_process_rate_limits() -> SingleProcessRateLimitBackend:
    return SingleProcessRateLimitBackend()


def single_pod(**overrides: object) -> dict[str, object]:
    """The keyword arguments of `create_app` that other pods would share: here the ones one process keeps alone."""
    links = PodLinks(
        rate_limits=in_process_rate_limits(),
        wake_channel=FakeWakeBus().pod(),
        place_store=InMemoryPlaceStore(),
        stream_leases=InMemoryLeases(),
    )
    return {"pods": replace(links, **overrides)}
