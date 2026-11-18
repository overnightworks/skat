"""A chair hold is stored, so it outlives the pod that started it: a killed pod's member loses the chair after the lapse
and the hold, once; a member who came back on the other pod keeps it; and a hold stored as both pods stop frees the
chair after their restart, while a member who never left keeps the chair, since nothing is held anew at a start.
"""

import time
from contextlib import suppress
from typing import TYPE_CHECKING

import httpx2
import pytest
from sqlalchemy import select

from skat.store.redis_clients import STREAM_LEASE_LASTS
from skat.store.schema import chair_holds
from skat.web.presence import HOLD_SWEEP_EVERY_SECONDS, LAPSE_SWEEP_EVERY, STREAM_RENEWAL_EVERY
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.pods import Pods, running_pods

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

pytestmark = [pytest.mark.postgres, pytest.mark.redis]

HOLD_SECONDS = 3
POLL_SECONDS = 0.5
# What a loaded runner may add to the lapse, the hold and the sweep.
MARGIN_SECONDS = 30
LAPSE_WITHIN_SECONDS = STREAM_LEASE_LASTS.total_seconds() + LAPSE_SWEEP_EVERY.total_seconds()
FREED_WITHIN_SECONDS = LAPSE_WITHIN_SECONDS + HOLD_SECONDS + HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS
# The last renewal is up to one renewal interval old when the pod dies, and the lease runs from it.
NOT_BEFORE_SECONDS = (STREAM_LEASE_LASTS - STREAM_RENEWAL_EVERY).total_seconds() - 1
# Long enough for any hold stored at the start to have been freed by a sweep.
KEPT_FOR_SECONDS = HOLD_SECONDS + 2 * HOLD_SWEEP_EVERY_SECONDS + 5
LEAVER_SEAT = 2


@pytest.fixture
def pods(postgres_template, tmp_path) -> Iterator[Pods]:
    with running_pods(postgres_template, tmp_path, chair_hold_seconds=HOLD_SECONDS) as running:
        yield running


def events_path(table_id: str) -> str:
    return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"


def leaver_at_a_new_table(pods: Pods) -> tuple[str, str, str]:
    """A table no hand was dealt at, its opener seated and never streaming, and the leaver in seat 2: the table's id,
    the opener's cookie and the leaver's.
    """
    opener_cookie, _ = pods.member()
    leaver_cookie, _ = pods.member()
    table_id = pods.table_opened_by(pods.first, opener_cookie)
    pods.sit(pods.first, leaver_cookie, table_id, LEAVER_SEAT)
    return table_id, opener_cookie, leaver_cookie


def occupants(pods: Pods, table_id: str, cookie: str) -> list[str | None]:
    return [chair["occupant_name"] for chair in pods.table_at(pods.first, table_id, cookie)["chairs"]]


def stored_holds(pods: Pods, table_id: str) -> frozenset[tuple[str, datetime]]:
    """Each stored hold at the table, as its account and the deadline the store keeps."""
    with pods.engine.connect() as connection:
        return frozenset(
            tuple(row)
            for row in connection.execute(
                select(chair_holds.c.account_id, chair_holds.c.due_at).where(chair_holds.c.table_id == table_id)
            )
        )


def seconds_until_the_leaver_is_freed(pods: Pods, table_id: str, cookie: str, within: float) -> float:
    since = time.monotonic()
    while occupants(pods, table_id, cookie)[LEAVER_SEAT - 1] is not None:
        assert time.monotonic() - since < within, "the leaver's chair was held for too long"
        time.sleep(POLL_SECONDS)
    return time.monotonic() - since


def test_a_member_whose_pod_died_loses_the_chair_after_the_lapse_and_the_hold_exactly_once(pods):
    table_id, opener_cookie, leaver_cookie = leaver_at_a_new_table(pods)
    freed_after = None

    with (
        suppress(httpx2.TransportError),
        pods.second.event_stream(events_path(table_id), within_seconds=FREED_WITHIN_SECONDS, cookie=leaver_cookie) as e,
    ):
        next(e)
        version = pods.table_at(pods.first, table_id, opener_cookie)["version"]
        pods.second.kill()
        freed_after = seconds_until_the_leaver_is_freed(pods, table_id, opener_cookie, FREED_WITHIN_SECONDS)

    assert freed_after is not None
    assert freed_after >= NOT_BEFORE_SECONDS
    assert pods.table_at(pods.first, table_id, opener_cookie)["version"] == version + 1


def test_a_member_who_came_back_on_the_other_pod_keeps_the_chair(pods):
    table_id, opener_cookie, leaver_cookie = leaver_at_a_new_table(pods)
    with pods.first.event_stream(events_path(table_id), within_seconds=KEPT_FOR_SECONDS, cookie=leaver_cookie) as e:
        next(e)

    with pods.second.event_stream(events_path(table_id), within_seconds=KEPT_FOR_SECONDS, cookie=leaver_cookie) as e:
        next(e)
        time.sleep(KEPT_FOR_SECONDS)
        seated = occupants(pods, table_id, opener_cookie)

    assert seated[LEAVER_SEAT - 1] is not None


def test_a_hold_stored_before_both_pods_restarted_frees_the_chair_at_its_deadline_and_no_chair_is_held_anew(pods):
    table_id, opener_cookie, leaver_cookie = leaver_at_a_new_table(pods)

    with (
        suppress(httpx2.TransportError),
        pods.first.event_stream(events_path(table_id), within_seconds=MARGIN_SECONDS, cookie=leaver_cookie) as e,
    ):
        next(e)
        stopped = time.monotonic()
        pods.stop_both()
    stored = stored_holds(pods, table_id)
    pods.start_both()
    started = time.monotonic()

    assert stored != frozenset()

    def holds_now() -> frozenset[tuple[str, datetime]]:
        now_stored = stored_holds(pods, table_id)
        assert now_stored in {stored, frozenset()}, "a start or a lapse stored the hold anew"
        return now_stored

    while holds_now() != frozenset():
        assert time.monotonic() - started < HOLD_SECONDS + HOLD_SWEEP_EVERY_SECONDS + 30, "the hold was kept too long"
        time.sleep(POLL_SECONDS)

    seconds_until_the_leaver_is_freed(pods, table_id, opener_cookie, HOLD_SECONDS + HOLD_SWEEP_EVERY_SECONDS + 30)
    assert time.monotonic() - stopped < HOLD_SECONDS + HOLD_SWEEP_EVERY_SECONDS + MARGIN_SECONDS
    while time.monotonic() < started + KEPT_FOR_SECONDS:
        holds_now()
        time.sleep(POLL_SECONDS)
    assert occupants(pods, table_id, opener_cookie)[0] is not None
