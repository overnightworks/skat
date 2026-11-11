from typing import TYPE_CHECKING

from webauth.single_process_stores import SingleProcessStores

from skat.web.sign_in import LoggingAuditSink

if TYPE_CHECKING:
    from webauth.ports import AuditSink


def in_memory_stores(audit: AuditSink | None = None) -> SingleProcessStores:
    return SingleProcessStores(audit=LoggingAuditSink() if audit is None else audit)
