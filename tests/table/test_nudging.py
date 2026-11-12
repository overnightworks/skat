"""A nudge asks a seat the table waits for once more: who may nudge which seat when, and what each viewer is shown."""

from typing import ClassVar

import pytest

from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.table.asking import ASK_AGAIN_AFTER
from skat.table.nudging import (
    NUDGES_PER_VERSION,
    NudgeRefusal,
    NudgeRequest,
    Nudges,
    NudgeState,
    is_retry,
    nudge_refusal,
    nudge_states,
    own_nudges,
)
from skat.table.records import HandProgress, TableOptions
from skat.table.views import view_of
from tests.support.open_chairs import PHASES, REARHAND_SEAT, sent_away
from tests.support.played_game import (
    asked_by_an_opponent,
    asked_by_the_declarer,
    between_games,
    declared_herz_hand,
    table_in,
)

MIDDLEHAND, REARHAND, FOREHAND = "account-middlehand", "account-rearhand", "account-forehand"
EVERYONE = (MIDDLEHAND, REARHAND, FOREHAND)
WATCHER = "account-watcher"
# The table is at version 7; seat 1 (middlehand) is on turn, seat 2 is rearhand and seat 3 forehand.
VERSION = 7
ON_TURN, SECOND, THIRD = 1, 2, 3


def kontra_hand():
    """The declared game at a table with Kontra: an opponent's word is open while forehand is on turn."""
    options = TableOptions(
        kontra=KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD)
    )
    return table_in(declared_herz_hand(), options)


def view_for(table, account, connected=EVERYONE):
    return view_of(table, account, frozenset((*connected, WATCHER)))


def request(seat=ON_TURN, *, version=VERSION, nudges=0):
    return NudgeRequest(version=version, seat=seat, nudges=nudges)


def refusal_for(account, asked, *, table=None, waited=ASK_AGAIN_AFTER, nudged=None, connected=EVERYONE):
    view = view_for(table or table_in(HandProgress()), account, connected)
    return nudge_refusal(view, asked, waited, nudged or {})


class TestWhoMayNudgeWhichSeatWhen:
    @pytest.mark.parametrize(
        ("account", "asked", "refusal"),
        [
            pytest.param(REARHAND, request(), None, id="a-seated-player-nudges-the-seat-on-turn"),
            pytest.param(FOREHAND, request(), None, id="so-does-the-other-one"),
            pytest.param(WATCHER, request(), NudgeRefusal.NOT_SEATED, id="a-watcher-may-not"),
            pytest.param(REARHAND, request(version=VERSION - 1), NudgeRefusal.STALE_VERSION, id="an-older-version"),
            pytest.param(REARHAND, request(SECOND), NudgeRefusal.OWN_SEAT, id="not-the-own-seat"),
            pytest.param(REARHAND, request(THIRD), NudgeRefusal.NOT_WAITING, id="a-seat-the-table-does-not-wait-for"),
            pytest.param(REARHAND, request(9), NudgeRefusal.NOT_WAITING, id="a-seat-that-is-no-chair"),
            pytest.param(MIDDLEHAND, request(), NudgeRefusal.OWN_SEAT, id="the-awaited-seat-not-itself"),
        ],
    )
    def test_the_viewer_of_the_table_is_refused_or_not(self, account, asked, refusal):
        assert refusal_for(account, asked) is refusal

    def test_the_chair_that_is_away_is_not_nudged(self):
        assert refusal_for(REARHAND, request(), connected=(REARHAND, FOREHAND)) is NudgeRefusal.AWAY

    def test_no_seat_is_nudged_while_a_chair_of_the_hand_is_open(self):
        open_chair = sent_away(PHASES["auction"](), REARHAND_SEAT)

        asked = request(version=open_chair.version)

        assert refusal_for(FOREHAND, asked, table=open_chair) is NudgeRefusal.SEAT_OPEN

    def test_a_seat_with_only_a_kontra_word_open_is_not_waited_for_but_the_seat_on_turn_is(self):
        table = kontra_hand()

        assert refusal_for(MIDDLEHAND, request(SECOND), table=table) is NudgeRefusal.NOT_WAITING
        assert refusal_for(MIDDLEHAND, request(THIRD), table=table) is None

    def test_an_opponents_give_up_waits_for_the_declarer_and_both_opponents_may_nudge_him(self):
        table = asked_by_an_opponent()

        assert [refusal_for(account, request(), table=table) for account in (REARHAND, FOREHAND)] == [None, None]
        assert refusal_for(REARHAND, request(THIRD), table=table) is NudgeRefusal.NOT_WAITING

    @pytest.mark.parametrize(
        "table", [asked_by_the_declarer(None), between_games()], ids=["a-give-up-question", "a-result"]
    )
    def test_each_of_two_awaited_seats_is_nudged_by_the_seats_beside_it_awaited_or_not(self, table):
        assert refusal_for(REARHAND, request(THIRD), table=table) is None
        assert refusal_for(FOREHAND, request(SECOND), table=table) is None


class TestTheMinute:
    def test_the_first_nudge_is_offered_once_the_table_has_waited_the_minute(self):
        assert refusal_for(REARHAND, request(), waited=ASK_AGAIN_AFTER) is None
        assert refusal_for(REARHAND, request(), waited=ASK_AGAIN_AFTER - 0.1) is NudgeRefusal.TOO_EARLY

    def test_the_second_nudge_is_offered_a_minute_after_the_first(self):
        first = {ON_TURN: Nudges(count=1, by_seat=SECOND, waited=ASK_AGAIN_AFTER + 5)}
        second = request(nudges=1)

        assert refusal_for(FOREHAND, second, waited=2 * ASK_AGAIN_AFTER + 4.9, nudged=first) is (
            NudgeRefusal.ALREADY_NUDGED
        )
        assert refusal_for(FOREHAND, second, waited=2 * ASK_AGAIN_AFTER + 5, nudged=first) is None

    def test_no_nudge_follows_the_cap(self):
        spent = {ON_TURN: Nudges(count=NUDGES_PER_VERSION, by_seat=SECOND, waited=ASK_AGAIN_AFTER)}

        assert refusal_for(FOREHAND, request(nudges=2), waited=1000, nudged=spent) is NudgeRefusal.ALREADY_NUDGED


class TestARetry:
    nudged: ClassVar = {ON_TURN: Nudges(count=1, by_seat=SECOND, waited=ASK_AGAIN_AFTER)}

    @pytest.mark.parametrize(
        ("account", "asked", "retry"),
        [
            pytest.param(REARHAND, request(nudges=0), True, id="the-same-nudger-with-the-count-it-saw-before"),
            pytest.param(REARHAND, request(nudges=1), False, id="the-same-nudger-who-saw-the-nudge"),
            pytest.param(FOREHAND, request(nudges=0), False, id="another-nudger"),
        ],
    )
    def test_is_the_nudge_the_nudger_already_made(self, account, asked, retry):
        assert is_retry(view_for(table_in(HandProgress()), account), asked, self.nudged) is retry

    def test_is_answered_as_no_refusal_even_while_the_next_nudge_is_not_offered(self):
        view = view_for(table_in(HandProgress()), REARHAND)

        assert nudge_refusal(view, request(nudges=0), ASK_AGAIN_AFTER, self.nudged) is None

    def test_is_refused_once_the_table_moved_on(self):
        view = view_for(table_in(HandProgress()), REARHAND)

        assert nudge_refusal(view, request(version=VERSION - 1), ASK_AGAIN_AFTER, self.nudged) is (
            NudgeRefusal.STALE_VERSION
        )


def states_for(account, *, table=None, nudged=None, connected=EVERYONE):
    return nudge_states(view_for(table or table_in(HandProgress()), account, connected), nudged or {})


class TestWhatEachViewerIsShown:
    def test_a_seated_viewer_who_may_nudge_sees_the_awaited_chair_open_to_a_nudge(self):
        assert [states_for(account) for account in (REARHAND, FOREHAND)] == [
            {ON_TURN: NudgeState(nudges=0, may_nudge=True, by_seat=None)}
        ] * 2

    def test_the_awaited_seat_and_a_watcher_see_nothing_until_it_is_nudged(self):
        assert (states_for(MIDDLEHAND), states_for(WATCHER)) == ({}, {})

    def test_a_nudge_is_seen_by_all_and_the_nudger_is_named_to_the_nudged_seat_only(self):
        nudged = {ON_TURN: Nudges(count=1, by_seat=SECOND, waited=ASK_AGAIN_AFTER)}

        assert {account: states_for(account, nudged=nudged) for account in (MIDDLEHAND, FOREHAND, WATCHER)} == {
            MIDDLEHAND: {ON_TURN: NudgeState(nudges=1, may_nudge=False, by_seat=SECOND)},
            FOREHAND: {ON_TURN: NudgeState(nudges=1, may_nudge=True, by_seat=None)},
            WATCHER: {ON_TURN: NudgeState(nudges=1, may_nudge=False, by_seat=None)},
        }

    def test_nobody_may_nudge_once_the_cap_is_spent(self):
        spent = {ON_TURN: Nudges(count=NUDGES_PER_VERSION, by_seat=THIRD, waited=2 * ASK_AGAIN_AFTER)}

        assert states_for(REARHAND, nudged=spent) == {
            ON_TURN: NudgeState(nudges=NUDGES_PER_VERSION, may_nudge=False, by_seat=None)
        }

    def test_the_chair_that_is_away_shows_no_state(self):
        assert states_for(REARHAND, connected=(REARHAND, FOREHAND)) == {}

    def test_no_chair_shows_a_state_while_a_chair_of_the_hand_is_open(self):
        assert states_for(FOREHAND, table=sent_away(PHASES["auction"](), REARHAND_SEAT)) == {}

    def test_each_of_two_awaited_seats_has_its_own_state_but_the_own_chair_none(self):
        table = asked_by_the_declarer(None)
        awaiting = NudgeState(nudges=0, may_nudge=True, by_seat=None)

        assert states_for(MIDDLEHAND, table=table) == {SECOND: awaiting, THIRD: awaiting}
        assert states_for(REARHAND, table=table) == {THIRD: awaiting}

    def test_an_opponents_give_up_shows_the_declarers_chair_alone(self):
        assert list(states_for(REARHAND, table=asked_by_an_opponent())) == [ON_TURN]

    def test_a_seat_with_only_a_kontra_word_open_shows_no_state_to_anyone(self):
        table = kontra_hand()

        assert [list(states_for(account, table=table)) for account in (MIDDLEHAND, REARHAND, FOREHAND, WATCHER)] == [
            [THIRD],
            [THIRD],
            [],
            [],
        ]

    def test_the_nudges_of_the_own_chair_are_those_the_revision_adds(self):
        nudged = {ON_TURN: Nudges(count=2, by_seat=THIRD, waited=2 * ASK_AGAIN_AFTER)}
        own = view_for(table_in(HandProgress()), MIDDLEHAND)
        other = view_for(table_in(HandProgress()), REARHAND)

        assert [own_nudges(view, nudge_states(view, nudged)) for view in (own, other)] == [2, 0]
