from typing import TYPE_CHECKING

from webauth.rate_limit import SingleProcessRateLimitBackend
from webauth.single_process_stores import SingleProcessStores

from skat.web.sign_in import LoggingAuditSink

if TYPE_CHECKING:
    from webauth.ports import AuditSink


def in_memory_stores(audit: AuditSink | None = None) -> SingleProcessStores:
    return SingleProcessStores(audit=LoggingAuditSink() if audit is None else audit)


def in_process_rate_limits() -> SingleProcessRateLimitBackend:
    return SingleProcessRateLimitBackend()


def single_pod(**overrides: object) -> dict[str, object]:
    """The keyword arguments of `create_app` that other pods would share: here the ones one process keeps alone."""
    return {"rate_limits": in_process_rate_limits(), **overrides}
