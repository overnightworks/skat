"""An empty table's wait is stored on its row, so it outlives the pod that stamped it: any pod ends the table once when
the wait is up and nobody is connected, a pod that died or a restart of both gives the table no fresh wait, and a
table somebody is at, or was dealt on, is never ended.
"""

import time
from contextlib import suppress
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx2
import pytest

from skat.store.redis_clients import STREAM_LEASE_LASTS
from skat.table.records import EndReason
from skat.web.presence import HOLD_SWEEP_EVERY_SECONDS, LAPSE_SWEEP_EVERY
from tests.support.pods import Pods, running_pods

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

EMPTY_TABLE_SECONDS = 6
POLL_SECONDS = 0.2
# What a loaded runner may add to the wait, the sweep and a lease's lapse.
MARGIN_SECONDS = 30
ENDED_WITHIN_SECONDS = EMPTY_TABLE_SECONDS + HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS
LAPSED_WITHIN_SECONDS = STREAM_LEASE_LASTS.total_seconds() + LAPSE_SWEEP_EVERY.total_seconds() + MARGIN_SECONDS
WAIT = timedelta(seconds=EMPTY_TABLE_SECONDS)


@pytest.fixture
def pods(postgres_template, tmp_path) -> Iterator[Pods]:
    with running_pods(postgres_template, tmp_path, empty_table_seconds=EMPTY_TABLE_SECONDS) as running:
        yield running


def a_table_somebody_visited(pods: Pods, cookie: str) -> str:
    """The id of an undealt table whose opener opened a stream at it on the first pod and closed it."""
    table_id = pods.table_opened_by(pods.first, cookie)
    with pods.first.event_stream(pods.events_path(table_id), within_seconds=ENDED_WITHIN_SECONDS, cookie=cookie) as e:
        next(e)
    return table_id


def wait_until_ended(pods: Pods, table_id: str, within: float = ENDED_WITHIN_SECONDS):
    since = time.monotonic()
    while pods.table_row(table_id).ended_at is None:
        assert time.monotonic() - since < within, "the empty table was not ended in time"
        time.sleep(POLL_SECONDS)
    return pods.table_row(table_id)


def wait_until_stamped(pods: Pods, table_id: str, within: float = LAPSED_WITHIN_SECONDS):
    since = time.monotonic()
    while pods.table_row(table_id).empty_since is None:
        assert time.monotonic() - since < within, "nobody-was-there was not stored in time"
        time.sleep(POLL_SECONDS)
    return pods.table_row(table_id).empty_since


def wait_until_cleared(pods: Pods, table_id: str, within: float = HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS) -> None:
    since = time.monotonic()
    while pods.table_row(table_id).empty_since is not None:
        assert time.monotonic() - since < within, "the stamp was not cleared in time"
        time.sleep(POLL_SECONDS)


def assert_ended_once_for_its_wait(pods: Pods, table_id: str, stamp, ended) -> None:
    assert ended.end_reason == EndReason.EMPTY.value
    assert ended.empty_seconds == EMPTY_TABLE_SECONDS
    assert ended.ended_at >= stamp + WAIT
    time.sleep(2 * HOLD_SWEEP_EVERY_SECONDS)
    assert pods.table_row(table_id).ended_at == ended.ended_at


def test_a_table_nobody_is_at_ends_once_after_its_wait_counted_from_the_last_leave(pods):
    table_id = a_table_somebody_visited(pods, pods.member()[0])

    stamp = wait_until_stamped(pods, table_id)
    ended = wait_until_ended(pods, table_id)

    assert_ended_once_for_its_wait(pods, table_id, stamp, ended)
    assert ended.ended_at <= stamp + WAIT + timedelta(seconds=HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS)


def test_a_pod_killed_during_the_wait_leaves_the_end_to_the_other_pod(pods):
    table_id = a_table_somebody_visited(pods, pods.member()[0])
    stamp = wait_until_stamped(pods, table_id)
    pods.first.kill()

    ended = wait_until_ended(pods, table_id)

    assert_ended_once_for_its_wait(pods, table_id, stamp, ended)


def test_both_pods_restarted_during_the_wait_end_the_table_at_the_old_stamp_plus_the_wait(pods):
    table_id = a_table_somebody_visited(pods, pods.member()[0])
    stamp = wait_until_stamped(pods, table_id)
    pods.settle_leases()
    pods.stop_both()
    while pods.database_now() < stamp + WAIT:
        time.sleep(POLL_SECONDS)
    pods.start_both()
    restarted = time.monotonic()

    ended = wait_until_ended(pods, table_id, HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS)

    assert pods.table_row(table_id).empty_since == stamp
    assert time.monotonic() - restarted < EMPTY_TABLE_SECONDS + HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS
    assert_ended_once_for_its_wait(pods, table_id, stamp, ended)


def test_a_visit_during_the_wait_clears_the_stamp_and_the_next_leave_starts_a_full_wait(pods):
    cookie = pods.member()[0]
    table_id = a_table_somebody_visited(pods, cookie)
    wait_until_stamped(pods, table_id)

    with pods.second.event_stream(pods.events_path(table_id), within_seconds=ENDED_WITHIN_SECONDS, cookie=cookie) as e:
        next(e)
        assert pods.table_row(table_id).empty_since is None
        time.sleep(EMPTY_TABLE_SECONDS + HOLD_SWEEP_EVERY_SECONDS)
        assert pods.table_row(table_id).ended_at is None
    second_stamp = wait_until_stamped(pods, table_id)
    ended = wait_until_ended(pods, table_id)

    assert_ended_once_for_its_wait(pods, table_id, second_stamp, ended)


def test_a_stamp_left_while_somebody_is_at_the_table_is_cleared_and_never_ends_it(pods):
    cookie = pods.member()[0]
    table_id = pods.table_opened_by(pods.first, cookie)
    with pods.first.event_stream(pods.events_path(table_id), within_seconds=ENDED_WITHIN_SECONDS, cookie=cookie) as e:
        next(e)
        pods.set_empty_since(table_id, pods.database_now() - 10 * WAIT)

        wait_until_cleared(pods, table_id)

        assert pods.table_row(table_id).ended_at is None
    second_stamp = wait_until_stamped(pods, table_id)
    ended = wait_until_ended(pods, table_id)

    assert_ended_once_for_its_wait(pods, table_id, second_stamp, ended)


def test_a_pod_killed_with_the_only_streams_leaves_the_table_to_end_once_after_the_lease_lapsed(pods):
    cookie = pods.member()[0]
    table_id = pods.table_opened_by(pods.first, cookie)
    with (
        suppress(httpx2.TransportError),
        pods.first.event_stream(pods.events_path(table_id), within_seconds=LAPSED_WITHIN_SECONDS, cookie=cookie) as e,
    ):
        next(e)
        pods.first.kill()
        stamp = wait_until_stamped(pods, table_id)

    ended = wait_until_ended(pods, table_id)

    assert_ended_once_for_its_wait(pods, table_id, stamp, ended)


def test_a_pod_started_stamps_an_undealt_table_nobody_is_at_that_has_no_stamp_and_ends_it_once(pods):
    table_id = pods.table_opened_by(pods.first, pods.member()[0])
    pods.set_empty_since(table_id, None)
    pods.settle_leases()
    pods.stop_both()
    pods.start_both()

    stamp = wait_until_stamped(pods, table_id, MARGIN_SECONDS)
    ended = wait_until_ended(pods, table_id)

    assert_ended_once_for_its_wait(pods, table_id, stamp, ended)


def test_a_pod_started_leaves_a_table_somebody_streams_at_on_the_other_pod_unstamped(pods):
    cookie = pods.member()[0]
    table_id = pods.table_opened_by(pods.first, cookie)
    control_id = pods.table_opened_by(pods.first, pods.member()[0])
    pods.set_empty_since(control_id, None)
    with pods.second.event_stream(pods.events_path(table_id), within_seconds=ENDED_WITHIN_SECONDS, cookie=cookie) as e:
        next(e)
        wait_until_cleared(pods, table_id)
        pods.settle_leases()
        pods.first.stop()
        pods.first.start()
        # The start note stamps the control table nobody is at, so it has run before the window opens.
        wait_until_stamped(pods, control_id, MARGIN_SECONDS)

        # The sweep clears a stamp once the wait is up, so a stamp of the start shows within the wait.
        stamped_within_the_wait = []
        since = time.monotonic()
        while time.monotonic() - since < EMPTY_TABLE_SECONDS - 1:
            stamped_within_the_wait.append(pods.table_row(table_id).empty_since)
            time.sleep(POLL_SECONDS)

        assert stamped_within_the_wait == [None] * len(stamped_within_the_wait)
        assert pods.table_row(table_id).ended_at is None


def test_a_dealt_table_everybody_left_is_never_ended_by_the_empty_wait(pods):
    table_id, cookies = pods.three_seated()
    with pods.first.event_stream(
        pods.events_path(table_id), within_seconds=ENDED_WITHIN_SECONDS, cookie=cookies[0]
    ) as e:
        next(e)

    time.sleep(EMPTY_TABLE_SECONDS + 2 * HOLD_SWEEP_EVERY_SECONDS)

    row = pods.table_row(table_id)
    assert (row.empty_since, row.ended_at) == (None, None)
