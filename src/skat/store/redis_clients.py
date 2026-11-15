"""The clients of the Redis every pod shares: the limits webauth spends and the channel tandem wakes the pods on."""

from typing import Final

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.retry import Retry as AsyncRetry
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from tandem import WakeChannel
from webauth.rate_limit import RedisRateLimitBackend

RATE_LIMIT_KEY_PREFIX: Final = "skat:rate"
WAKE_KEY_PREFIX: Final = "skat"

# A limit check holds its worker thread until the client gives up, so the timeouts are short and the retries few: an
# outage answers 503 at once and pins no thread.
_RATE_LIMIT_TIMEOUT_SECONDS: Final = 0.5
_RATE_LIMIT_RETRIES: Final = 1
# A publish that stalls only holds a task of its own, and a loaded Redis may need a moment to answer it.
_WAKE_TIMEOUT_SECONDS: Final = 2.0
_WAKE_RETRIES: Final = 3


def shared_rate_limits(redis_url: str) -> RedisRateLimitBackend:
    """The sign-in and request limits that every pod spends from together."""
    # redis-py's `from_url` leaves its keyword arguments untyped.
    client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        redis_url,
        socket_timeout=_RATE_LIMIT_TIMEOUT_SECONDS,
        socket_connect_timeout=_RATE_LIMIT_TIMEOUT_SECONDS,
        retry=Retry(ExponentialBackoff(), _RATE_LIMIT_RETRIES),
    )
    return RedisRateLimitBackend(client, key_prefix=RATE_LIMIT_KEY_PREFIX)


def shared_wake_channel(redis_url: str) -> WakeChannel:
    """The channel on which the pods tell one another what changed. The client's timeouts let a publish fail on a
    Redis that stays silent, and its retry lets a pod's re-read at a resubscribe survive a Redis restart.
    """
    client = AsyncRedis.from_url(  # pyright: ignore[reportUnknownMemberType]
        redis_url,
        socket_timeout=_WAKE_TIMEOUT_SECONDS,
        socket_connect_timeout=_WAKE_TIMEOUT_SECONDS,
        retry=AsyncRetry(ExponentialBackoff(), _WAKE_RETRIES),
    )
    return WakeChannel(client, key_prefix=WAKE_KEY_PREFIX)
