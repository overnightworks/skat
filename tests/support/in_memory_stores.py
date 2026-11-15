from typing import TYPE_CHECKING

from redis.exceptions import ConnectionError as RedisConnectionError
from webauth.rate_limit import SingleProcessRateLimitBackend
from webauth.single_process_stores import SingleProcessStores

from skat.web.sign_in import LoggingAuditSink
from tests.support.loopback_wake_channel import single_pod_channel

if TYPE_CHECKING:
    from webauth.ports import AuditSink


def in_memory_stores(audit: AuditSink | None = None) -> SingleProcessStores:
    return SingleProcessStores(audit=LoggingAuditSink() if audit is None else audit)


def in_process_rate_limits() -> SingleProcessRateLimitBackend:
    return SingleProcessRateLimitBackend()


class RateLimitsThatCanFail:
    """The limits of one process, which fail from the moment `fail` is called, as an unreachable Redis does."""

    def __init__(self) -> None:
        self._limits = in_process_rate_limits()
        self._failing = False

    def fail(self) -> None:
        self._failing = True

    def is_allowed(self, key: str, *, limit: int, window_seconds: int) -> bool:
        if self._failing:
            message = "the limits' Redis cannot be reached"
            raise RedisConnectionError(message)
        return self._limits.is_allowed(key, limit=limit, window_seconds=window_seconds)


def single_pod(**overrides: object) -> dict[str, object]:
    """The keyword arguments of `create_app` that other pods would share: here the ones one process keeps alone."""
    return {"rate_limits": in_process_rate_limits(), "wake_channel": single_pod_channel(), **overrides}
