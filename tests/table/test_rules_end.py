from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from skat.table.ending import decide_close
from skat.table.records import Actor, Refusal
from skat.table.rules import ends_unplayed, unplayed_end
from tests.support.played_game import declared_herz_hand, table_in

DAYS = 90
LAST_PLAYED_AT = datetime(2026, 8, 1, 18, 30, tzinfo=UTC)
LINE = LAST_PLAYED_AT + timedelta(days=DAYS)


@pytest.fixture
def dealt():
    return table_in(declared_herz_hand())


class TestAnUnplayedTableEnds:
    @pytest.mark.parametrize(
        ("now", "ends"),
        [
            pytest.param(LINE - timedelta(seconds=1), False, id="one-second-before-the-end"),
            pytest.param(LINE, True, id="exactly-at-the-end"),
            pytest.param(LINE + timedelta(seconds=1), True, id="one-second-after-the-end"),
        ],
    )
    def test_exactly_at_the_instant_the_paused_list_names(self, dealt, now, ends):
        assert ends_unplayed(dealt, LAST_PLAYED_AT, now, DAYS) is ends

    def test_a_running_hand_does_not_hold_it_back(self, dealt):
        assert dealt.hand is not None
        assert ends_unplayed(dealt, LAST_PLAYED_AT, LINE, DAYS) is True

    def test_a_table_on_which_no_hand_was_dealt_never_does(self, dealt):
        undealt = replace(dealt, dealer=None, hand=None)

        assert ends_unplayed(undealt, None, LINE + timedelta(days=1000), DAYS) is False

    def test_a_longer_setting_moves_the_end(self, dealt):
        assert ends_unplayed(dealt, LAST_PLAYED_AT, LINE, DAYS + 1) is False


class TestTheEndInstant:
    def test_is_the_last_played_time_plus_the_days(self):
        assert unplayed_end(LAST_PLAYED_AT, DAYS) == LINE

    def test_is_in_utc_whatever_zone_the_time_came_in(self):
        in_vienna = LAST_PLAYED_AT.astimezone(timezone(timedelta(hours=1)))

        assert unplayed_end(in_vienna, DAYS).utcoffset() == timedelta(0)
        assert unplayed_end(in_vienna, DAYS) == LINE


class TestOnlyTheOpenerCloses:
    OPENER = Actor(account_id="account-opener", display_name="Anna")

    @pytest.mark.parametrize(
        ("actor", "refusal"),
        [
            pytest.param(OPENER, None, id="the-opener"),
            pytest.param(Actor("account-seated", "Ben"), Refusal.NOT_ALLOWED, id="a-seated-person"),
            pytest.param(Actor("account-watcher", "Cleo"), Refusal.NOT_ALLOWED, id="a-watcher"),
        ],
    )
    def test_refuses_everyone_but_the_account_that_opened_the_table(self, actor, refusal):
        assert decide_close(self.OPENER.account_id, actor) is refusal

    def test_refuses_everyone_for_a_table_with_no_known_opener(self):
        assert decide_close(None, self.OPENER) is Refusal.NOT_ALLOWED
