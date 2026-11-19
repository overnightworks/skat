from datetime import UTC, datetime, timedelta

import pytest

from skat.table.records import TurnStatement
from skat.table.turn_state import THINKING_CAP_SECONDS, TurnStateView, turn_state_view_of

STATED_AT = datetime(2026, 11, 19, 12, tzinfo=UTC)


def thinking_for(seconds):
    return turn_state_view_of(TurnStatement(None, True, STATED_AT), STATED_AT + timedelta(seconds=seconds))


@pytest.mark.parametrize(
    ("statement", "shown"),
    [
        (None, None),
        (TurnStatement(None, False, STATED_AT), None),
        (TurnStatement("busy", False, STATED_AT), TurnStateView("busy", None)),
        (TurnStatement("budget_spent", False, STATED_AT), TurnStateView("budget_spent", None)),
    ],
    ids=["nothing stated", "turns that answer", "a busy stop", "a spent budget"],
)
def test_a_stop_shows_as_stated_and_nothing_stated_shows_nothing(statement, shown):
    assert turn_state_view_of(statement, STATED_AT + timedelta(days=1)) == shown


@pytest.mark.parametrize(
    ("seconds", "left"),
    [(0, THINKING_CAP_SECONDS), (0.2, THINKING_CAP_SECONDS), (30.5, THINKING_CAP_SECONDS - 30), (119.5, 1)],
)
def test_thinking_shows_the_whole_seconds_left_under_the_cap_rounded_up(seconds, left):
    assert thinking_for(seconds) == TurnStateView(None, left)


@pytest.mark.parametrize("seconds", [THINKING_CAP_SECONDS, THINKING_CAP_SECONDS + 0.1, 3600])
def test_thinking_shows_nothing_once_the_cap_is_reached(seconds):
    assert thinking_for(seconds) is None


def test_a_statement_stamped_ahead_of_the_clock_shows_no_more_than_the_cap():
    assert thinking_for(-30) == TurnStateView(None, THINKING_CAP_SECONDS)


def test_thinking_cannot_be_placed_without_a_clock_and_shows_nothing():
    assert turn_state_view_of(TurnStatement(None, True, STATED_AT), None) is None
