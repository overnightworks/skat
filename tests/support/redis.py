import os
from urllib.parse import urlsplit

import pytest
from redis import Redis

URL_ENVIRONMENT_VARIABLE = "SKAT_TEST_REDIS_URL"
UNDISTRIBUTED_WORKER = "master"
WORKER_PREFIX = "gw"


def server_url() -> str:
    """The throwaway server's URL; `scripts/test_stores.sh` and CI's service provide it."""
    url = os.environ.get(URL_ENVIRONMENT_VARIABLE)
    if not url:
        pytest.fail(f"{URL_ENVIRONMENT_VARIABLE} names no Redis; run the tests through scripts/test_stores.sh")
    return url


def _worker_index() -> int:
    worker = os.environ.get("PYTEST_XDIST_WORKER", UNDISTRIBUTED_WORKER)
    return 0 if worker == UNDISTRIBUTED_WORKER else int(worker.removeprefix(WORKER_PREFIX))


def fresh_database_url() -> str:
    """The URL of this xdist worker's own Redis database, emptied, so that keys never cross tests or workers."""
    index = _worker_index()
    url = urlsplit(server_url())._replace(path=f"/{index}").geturl()
    with Redis.from_url(url) as redis:
        databases = int(redis.config_get("databases")["databases"])
        if index >= databases:
            pytest.fail(f"worker {index} has no Redis database of its own among {databases}; run fewer workers")
        redis.flushdb()
    return url
