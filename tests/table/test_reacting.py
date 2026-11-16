"""A reaction is thrown by anyone at the table, seated or watching, and each person only so often."""

import pytest

from skat.table.reacting import (
    REACTION_WINDOW_SECONDS,
    REACTIONS_PER_WINDOW,
    ReactionRefusal,
    reaction_refusal,
    throwing_seat,
)
from skat.table.records import HandProgress
from skat.table.views import view_of
from tests.support.played_game import table_in

SEATED, WATCHER, STRANGER = "account-middlehand", "account-watcher", "account-stranger"
NOW = 1000.0


def refusal_for(account, *, watching=None, thrown_at=(), now=NOW):
    view = view_of(table_in(HandProgress()), account, frozenset((SEATED, WATCHER)))
    return reaction_refusal(
        view, watching=account == WATCHER if watching is None else watching, thrown_at=thrown_at, now=now
    )


class TestWhoMayThrow:
    @pytest.mark.parametrize(
        ("account", "watching", "refusal"),
        [
            pytest.param(SEATED, False, None, id="a-seated-person-with-no-stream-open"),
            pytest.param(SEATED, True, None, id="a-seated-person-watching-too"),
            pytest.param(WATCHER, True, None, id="a-watcher"),
            pytest.param(STRANGER, False, ReactionRefusal.NOT_AT_THE_TABLE, id="a-stranger-with-the-table-closed"),
        ],
    )
    def test_anyone_who_sits_or_watches_may_throw(self, account, watching, refusal):
        assert refusal_for(account, watching=watching) is refusal

    def test_a_seated_person_throws_from_the_own_seat_and_a_watcher_from_none(self):
        views = [view_of(table_in(HandProgress()), account, frozenset()) for account in (SEATED, WATCHER)]

        assert [throwing_seat(view) for view in views] == [1, None]


class TestHowOften:
    def test_a_person_throws_the_limit_within_the_window_and_the_next_one_is_refused(self):
        within = [NOW - 1] * (REACTIONS_PER_WINDOW - 1)

        assert refusal_for(SEATED, thrown_at=within) is None
        assert refusal_for(SEATED, thrown_at=[*within, NOW - 1]) is ReactionRefusal.TOO_FAST

    def test_a_throw_leaves_the_count_once_the_window_has_passed(self):
        thrown = [NOW - REACTION_WINDOW_SECONDS] * REACTIONS_PER_WINDOW

        assert refusal_for(SEATED, thrown_at=thrown) is None
        assert refusal_for(SEATED, thrown_at=[thrown[0] + 0.1] * REACTIONS_PER_WINDOW) is ReactionRefusal.TOO_FAST

    def test_a_stranger_is_refused_as_not_at_the_table_before_the_count_is_read(self):
        thrown = [NOW] * REACTIONS_PER_WINDOW

        assert refusal_for(STRANGER, watching=False, thrown_at=thrown) is ReactionRefusal.NOT_AT_THE_TABLE
