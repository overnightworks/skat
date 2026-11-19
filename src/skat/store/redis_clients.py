"""The clients of the Redis every pod shares: the limits webauth spends, the channel tandem wakes the pods on, the
leases that count who watches a table, the place store agents keeps its listen record in and the record of what an
agent's token says of it.
"""

from datetime import timedelta
from typing import Final

from agents.mcp_server.redis_place_store import RedisPlaceStore
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.retry import Retry as AsyncRetry
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from tandem import Leases, WakeChannel
from webauth.rate_limit import RedisRateLimitBackend

from skat.store.redis_agent_records import RedisAgentRecords

RATE_LIMIT_KEY_PREFIX: Final = "skat:rate"
WAKE_KEY_PREFIX: Final = "skat"
AGENT_RECORD_KEY_PREFIX: Final = "skat-agent-record"
STREAM_LEASE_FAMILY: Final = "presence"
# A pod that dies loses its people from every read once this has passed since their last renewal; a claim on a lapse
# outlasts the slowest handling of it.
STREAM_LEASE_LASTS: Final = timedelta(seconds=30)
_STREAM_LEASE_CLAIM_FOR: Final = timedelta(seconds=60)

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


def _shared_async_client(redis_url: str) -> AsyncRedis:
    """The client of the wake channel, the place store and the agent records. Its timeouts let a publish fail on a
    Redis that stays silent, and its retry lets a pod's re-read at a resubscribe survive a Redis restart.
    """
    return AsyncRedis.from_url(  # pyright: ignore[reportUnknownMemberType]
        redis_url,
        socket_timeout=_WAKE_TIMEOUT_SECONDS,
        socket_connect_timeout=_WAKE_TIMEOUT_SECONDS,
        retry=AsyncRetry(ExponentialBackoff(), _WAKE_RETRIES),
    )


def shared_wake_channel(redis_url: str) -> WakeChannel:
    """The channel on which the pods tell one another what changed."""
    return WakeChannel(_shared_async_client(redis_url), key_prefix=WAKE_KEY_PREFIX)


def shared_stream_leases(redis_url: str) -> Leases:
    """The leases of the open streams, which tell every pod who watches which table."""
    return Leases(
        _shared_async_client(redis_url),
        key_prefix=WAKE_KEY_PREFIX,
        family=STREAM_LEASE_FAMILY,
        lasts=STREAM_LEASE_LASTS,
        claim_for=_STREAM_LEASE_CLAIM_FOR,
    )


def shared_place_store(redis_url: str) -> RedisPlaceStore:
    """The store that tells every pod which agents listen and what changed for them; agents keeps its keys and wakes
    under `<WAKE_KEY_PREFIX>-agents`, apart from the pods' own.
    """
    return RedisPlaceStore(_shared_async_client(redis_url), key_prefix=WAKE_KEY_PREFIX)


def shared_agent_records(redis_url: str) -> RedisAgentRecords:
    """The record of each agent's name and owner, which every pod writes at an agent's call and reads for its list."""
    return RedisAgentRecords(_shared_async_client(redis_url), key_prefix=AGENT_RECORD_KEY_PREFIX)
