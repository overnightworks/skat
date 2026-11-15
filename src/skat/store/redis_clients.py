"""The clients of the Redis every pod shares."""

from typing import Final

from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from webauth.rate_limit import RedisRateLimitBackend

RATE_LIMIT_KEY_PREFIX: Final = "skat:rate"

# A limit check holds its worker thread until the client gives up, so the timeouts are short and the retries few: an
# outage answers 503 at once and pins no thread.
_RATE_LIMIT_TIMEOUT_SECONDS: Final = 0.5
_RATE_LIMIT_RETRIES: Final = 1


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
