"""The pause before the next deal is stored, so it outlives the pod that wrote it: any pod deals the table once when
the pause is over and everybody is connected, a pod that died or a restart of both changes nothing about when, and a
deal that is not due is never made twice.
"""

import time
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING

import pytest

from skat.table.rules import NEXT_DEAL_PAUSE_SECONDS
from skat.web.presence import PAUSE_SWEEP_EVERY_SECONDS
from tests.support.pods import Pods, running_pods

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

# What a loaded runner may add to the pause and the sweep.
MARGIN_SECONDS = 30
DEALT_WITHIN_SECONDS = NEXT_DEAL_PAUSE_SECONDS + PAUSE_SWEEP_EVERY_SECONDS + MARGIN_SECONDS
POLL_SECONDS = 0.2
SETTLED_FOR_SECONDS = 2 * PAUSE_SWEEP_EVERY_SECONDS + 2


@pytest.fixture
def pods(postgres_template, tmp_path) -> Iterator[Pods]:
    with running_pods(postgres_template, tmp_path) as running:
        yield running


@contextmanager
def streaming(pods: Pods, process, table_id: str, cookies: list[str]) -> Iterator[None]:
    """Each of `cookies` has a stream open at the table on `process`."""
    with ExitStack() as streams:
        # Every reader stays referenced: a stream whose reader is dropped is closed.
        readers = [
            streams.enter_context(
                process.event_stream(pods.events_path(table_id), within_seconds=DEALT_WITHIN_SECONDS, cookie=cookie)
            )
            for cookie in cookies
        ]
        for reader in readers:
            next(reader)
        yield


def wait_until_dealt(pods: Pods, table_id: str, version: int) -> float:
    """The seconds until the table's version moves past `version`."""
    since = time.monotonic()
    while pods.table_row(table_id).version == version:
        assert time.monotonic() - since < DEALT_WITHIN_SECONDS, "the next hand was not dealt in time"
        time.sleep(POLL_SECONDS)
    return time.monotonic() - since


def assert_dealt_once_and_the_pause_spent(pods: Pods, table_id: str, version: int) -> None:
    time.sleep(SETTLED_FOR_SECONDS)
    assert pods.table_row(table_id).version == version + 1
    assert pods.next_deal_due_at(table_id) is None


def test_a_passed_in_table_is_dealt_once_between_the_pause_and_the_sweep_after_it(pods):
    table_id, cookies = pods.three_seated()
    with streaming(pods, pods.first, table_id, cookies):
        pods.pass_hand_in(pods.first, table_id, cookies)
        passed = time.monotonic()
        version = pods.table_row(table_id).version
        assert pods.next_deal_due_at(table_id) is not None

        wait_until_dealt(pods, table_id, version)

        assert time.monotonic() - passed >= NEXT_DEAL_PAUSE_SECONDS - 1
        assert_dealt_once_and_the_pause_spent(pods, table_id, version)


def test_a_stream_opening_during_the_pause_neither_moves_it_nor_stretches_it(pods):
    table_id, cookies = pods.three_seated()
    onlooker = pods.member()[0]
    with streaming(pods, pods.first, table_id, cookies):
        pods.pass_hand_in(pods.first, table_id, cookies)
        version = pods.table_row(table_id).version
        due_at = pods.next_deal_due_at(table_id)

        with streaming(pods, pods.second, table_id, [onlooker]):
            assert pods.next_deal_due_at(table_id) == due_at
            wait_until_dealt(pods, table_id, version)

        assert_dealt_once_and_the_pause_spent(pods, table_id, version)


def test_a_player_away_at_the_due_time_loses_the_pause_and_the_return_starts_a_new_one(pods):
    table_id, cookies = pods.three_seated()
    with streaming(pods, pods.first, table_id, cookies[:2]):
        with streaming(pods, pods.first, table_id, cookies[2:]):
            pods.pass_hand_in(pods.first, table_id, cookies)
        version = pods.table_row(table_id).version

        while pods.next_deal_due_at(table_id) is not None:
            time.sleep(POLL_SECONDS)
        assert pods.table_row(table_id).version == version

        with streaming(pods, pods.second, table_id, cookies[2:]):
            wait_until_dealt(pods, table_id, version)

    assert_dealt_once_and_the_pause_spent(pods, table_id, version)


def test_a_pod_killed_during_the_pause_leaves_the_deal_to_the_other_pod_once(pods):
    table_id, cookies = pods.three_seated()
    with streaming(pods, pods.first, table_id, cookies):
        pods.pass_hand_in(pods.first, table_id, cookies)
        version = pods.table_row(table_id).version
        due_at = pods.next_deal_due_at(table_id)
        pods.first.kill()

        with streaming(pods, pods.second, table_id, cookies):
            wait_until_dealt(pods, table_id, version)

    assert due_at is not None
    assert_dealt_once_and_the_pause_spent(pods, table_id, version)


def test_both_pods_restarted_during_the_pause_keep_its_deadline_and_deal_once(pods):
    table_id, cookies = pods.three_seated()
    with streaming(pods, pods.first, table_id, cookies):
        pods.pass_hand_in(pods.first, table_id, cookies)
        version = pods.table_row(table_id).version
        due_at = pods.next_deal_due_at(table_id)
        pods.stop_both()
    pods.start_both()

    assert pods.next_deal_due_at(table_id) == due_at
    with streaming(pods, pods.second, table_id, cookies):
        wait_until_dealt(pods, table_id, version)

    assert_dealt_once_and_the_pause_spent(pods, table_id, version)
