"""A table's proposal to end the series is asked after its minute whether it has lapsed: once for the minute, again for
what a proposal that still stands has left, again after a failure, and for every stored proposal at the server's start.
"""

import pytest
from agents.member import LEASE_SECONDS

from skat.web.end_answers import EndAnswers
from skat.web.presence import (
    CHAIR_RELEASE_RETRY_SECONDS,
    NEXT_DEAL_PAUSE_SECONDS,
    AgentLease,
    EmptyTable,
    NextDeal,
    Presence,
)
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.idle_presence import idle_wakes
from tests.support.in_memory_leases import InMemoryLeases
from tests.web.support.presence import FAILURE_NAMING_AN_ACCOUNT, TABLE, Notes, chair_hold, run

MINUTE = 60
ANOTHER_TABLE = "b" * 32


async def no_tables(_account_id):
    return []


@pytest.fixture
def presence(time, holds, deals, ends, lapses):
    return Presence(
        chair_hold(time, holds),
        NextDeal(NEXT_DEAL_PAUSE_SECONDS, deals.deal_next),
        EmptyTable(DEFAULT_EMPTY_TABLE_SECONDS, ends.end, Notes().note),
        AgentLease(LEASE_SECONDS, no_tables),
        idle_wakes(),
        InMemoryLeases(),
        EndAnswers(lapses.lapse),
    )


def test_a_proposal_is_asked_once_its_minute_has_passed(presence, time, lapses):
    presence.end_answer_watch.watch(TABLE, MINUTE)

    run(time.advance(MINUTE - 1))
    assert lapses.asked == []
    run(time.advance(1))

    assert lapses.asked == [TABLE]


def test_a_proposal_that_still_stands_is_asked_again_for_what_it_has_left(presence, time, lapses):
    lapses.left = [5.0]
    presence.end_answer_watch.watch(TABLE, MINUTE)

    run(time.advance(MINUTE))
    run(time.advance(4))
    assert lapses.asked == [TABLE]
    run(time.advance(1))

    assert lapses.asked == [TABLE, TABLE]


def test_a_failed_step_is_asked_again_after_the_retry_pause(presence, time, lapses):
    lapses.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
    presence.end_answer_watch.watch(TABLE, MINUTE)

    run(time.advance(MINUTE))
    run(time.advance(CHAIR_RELEASE_RETRY_SECONDS))

    assert lapses.asked == [TABLE, TABLE]


def test_the_server_start_arms_the_minute_each_stored_proposal_has_left(presence, time, lapses):
    presence.end_answer_watch.watch_all({TABLE: 0.0, ANOTHER_TABLE: 30.0})

    run(time.advance(0))
    assert lapses.asked == [TABLE]
    run(time.advance(30))

    assert lapses.asked == [TABLE, ANOTHER_TABLE]


def test_a_table_with_a_timer_waiting_that_falls_due_no_later_gets_no_second_one(presence, time, lapses):
    presence.end_answer_watch.watch(TABLE, MINUTE / 2)
    presence.end_answer_watch.watch_all({TABLE: MINUTE})

    run(time.advance(MINUTE))

    assert lapses.asked == [TABLE]


def test_a_deadline_found_earlier_than_the_waiting_timers_is_kept(presence, time, lapses):
    presence.end_answer_watch.watch(TABLE, MINUTE)

    presence.end_answer_watch.watch_all({TABLE: 45.0})
    run(time.advance(45))

    assert lapses.asked == [TABLE]


def test_a_timer_that_fell_due_after_a_newer_one_was_armed_leaves_the_newer_one_standing(presence, time, lapses):
    presence.end_answer_watch.watch(TABLE, MINUTE)
    presence.end_answer_watch.watch_all({TABLE: 45.0})
    run(time.advance(45))
    presence.end_answer_watch.watch(TABLE, MINUTE)

    run(time.advance(15))
    presence.end_answer_watch.watch(TABLE, 45.0)
    run(time.advance(45))

    assert lapses.asked == [TABLE, TABLE, TABLE]


def test_a_table_is_timed_again_once_its_timer_has_run(presence, time, lapses):
    presence.end_answer_watch.watch(TABLE, MINUTE)
    run(time.advance(MINUTE))

    presence.end_answer_watch.watch(TABLE, MINUTE)
    run(time.advance(MINUTE))

    assert lapses.asked == [TABLE, TABLE]


def test_a_stopped_presence_asks_nothing(presence, time, lapses):
    presence.stop()

    presence.end_answer_watch.watch(TABLE, MINUTE)
    run(time.advance(MINUTE))

    assert lapses.asked == []
