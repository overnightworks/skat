"""A pod that dies without a word loses its people from every other pod's count once their leases run out, and not
before: the watcher of the killed pod stays counted while its lease runs.
"""

import time
from contextlib import suppress
from typing import TYPE_CHECKING

import httpx2
import pytest

from skat.store.redis_clients import STREAM_LEASE_LASTS
from skat.web.presence import LAPSE_SWEEP_EVERY, STREAM_RENEWAL_EVERY
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.pods import Pods, running_pods

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

POLL_SECONDS = 0.5
# What a loaded runner may add to the sweep.
MARGIN_SECONDS = 10
WITHIN_SECONDS = STREAM_LEASE_LASTS.total_seconds() + LAPSE_SWEEP_EVERY.total_seconds() + MARGIN_SECONDS
# The last renewal is up to one renewal interval old when the pod dies, and the lease runs from it.
NOT_BEFORE_SECONDS = (STREAM_LEASE_LASTS - STREAM_RENEWAL_EVERY).total_seconds() - 1


@pytest.fixture(scope="module")
def pods(postgres_template, tmp_path_factory) -> Iterator[Pods]:
    with running_pods(postgres_template, tmp_path_factory.mktemp("pods")) as running:
        yield running


def test_a_killed_pods_watcher_is_counted_by_the_other_pod_until_its_lease_runs_out_and_not_longer(pods):
    opener_cookie, _ = pods.member()
    watcher_cookie, _ = pods.member()
    table_id = pods.table_opened_by(pods.first, opener_cookie)
    counted_before = None
    gone_after = None

    with (
        suppress(httpx2.TransportError),
        pods.second.event_stream(
            f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", within_seconds=WITHIN_SECONDS, cookie=watcher_cookie
        ) as events,
    ):
        next(events)
        counted_before = pods.watchers_at(pods.first, table_id, opener_cookie)
        killed = time.monotonic()
        pods.second.kill()
        while pods.watchers_at(pods.first, table_id, opener_cookie):
            assert time.monotonic() - killed < WITHIN_SECONDS, "the killed pod's watcher was counted for too long"
            time.sleep(POLL_SECONDS)
        gone_after = time.monotonic() - killed

    assert counted_before == 1
    assert gone_after is not None
    assert gone_after >= NOT_BEFORE_SECONDS
