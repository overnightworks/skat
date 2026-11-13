"""The seated players vote to abort a hand while one of its chairs is open: more than half of them end it."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Bid
from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.deal import Position
from skat.table.hand_abort import AbortVoteCommand, abort_vote_payload, decide_agree_to_abort, decide_refuse_to_abort
from skat.table.records import HandProgress, NewHand, OccupantKind, Refusal, Series, TableOptions
from skat.table.rules import (
    abort_agreed,
    decide_sit,
    decide_stand,
    hand_runs,
    next_deal_due,
    result_pending,
    series_games_left,
    series_over,
    waiting_seat_of,
)
from skat.table.send_away import decide_send_away
from skat.table.views import view_of
from tests.support.open_chairs import ALL_PASS, RAMSCH, actor_at, newcomer, sent_away
from tests.support.played_game import an_entry, table_in, with_agents

NOBODY = frozenset[str]()
ONE_BOCK_ROUND = BockRounds((3,))
BOCK_ON_EVERY_PASS = BockOptions(frozenset({BockTrigger.PASSED_IN}), BockOverlap.APPEND)


def standing(*open_seats: int, voted: tuple[int, ...] = (), **changes):
    """A hand in the auction whose chairs `open_seats` are free; `voted` seats said yes to aborting it."""
    table = table_in(HandProgress(auction=(Bid(Position.MIDDLEHAND, 18),), abort_yes=frozenset(voted)))
    chairs = tuple(replace(chair, occupant=None) if chair.seat in open_seats else chair for chair in table.chairs)
    return replace(table, chairs=chairs, **changes)


def agree(table, seat):
    return decide_agree_to_abort(table, actor_at(table, seat))


def is_aborted(table):
    return table.progress.aborted and not hand_runs(table)


class TestTheMajority:
    @pytest.mark.parametrize(
        ("seated", "yes", "agreed"),
        [
            pytest.param(1, 1, True, id="one-of-one"),
            pytest.param(2, 1, False, id="one-of-two"),
            pytest.param(2, 2, True, id="two-of-two"),
            pytest.param(3, 1, False, id="one-of-three"),
            pytest.param(3, 2, True, id="two-of-three"),
            pytest.param(1, 0, False, id="no-yes"),
        ],
    )
    def test_is_more_than_half_of_the_seated_chairs(self, seated, yes, agreed):
        open_seats = (3, 2, 1)[: 3 - seated]
        table = standing(*open_seats, voted=tuple(sorted(set(range(1, 4)) - set(open_seats)))[:yes])

        assert abort_agreed(table) is agreed


class TestAgree:
    def test_one_seated_chair_ends_the_hand_at_once(self):
        table = standing(2, 3)

        decision = agree(table, 1)

        assert (decision.refusal, is_aborted(decision.table), decision.table.version) == (None, True, table.version + 1)

    def test_the_first_of_two_proposes_and_the_second_ends_the_hand(self):
        table = standing(3)

        proposed = agree(table, 1).table
        ended = agree(proposed, 2).table

        assert (proposed.progress.abort_yes, hand_runs(proposed)) == (frozenset({1}), True)
        assert (ended.version, is_aborted(ended)) == (proposed.version + 1, True)

    def test_a_repeated_yes_changes_nothing(self):
        proposed = standing(3, voted=(1,))

        decision = agree(proposed, 1)

        assert (decision.table, decision.refusal) == (proposed, None)

    def test_the_hand_stands_still_so_a_vote_needs_no_version(self):
        table = standing(3)

        assert waiting_seat_of(table) == 3
        assert agree(table, 2).refusal is None

    def test_a_hand_with_no_open_chair_refuses_hand_not_open(self):
        table = standing()

        decision = agree(table, 1)

        assert (decision.refusal, decision.table) == (Refusal.HAND_NOT_OPEN, table)

    def test_a_person_who_is_not_seated_refuses_not_seated(self):
        assert decide_agree_to_abort(standing(3), newcomer()).refusal is Refusal.NOT_SEATED

    def test_a_table_with_no_hand_refuses_no_hand(self):
        between = replace(standing(3), hand=None, progress=HandProgress())

        assert agree(between, 1).refusal is Refusal.NO_HAND


class TestRefuse:
    def test_a_no_clears_the_proposal_and_the_hand_waits(self):
        proposed = standing(3, voted=(1,))

        decision = decide_refuse_to_abort(proposed, actor_at(proposed, 2))

        assert decision.refusal is None
        assert (decision.table.progress.abort_yes, hand_runs(decision.table)) == (frozenset(), True)
        assert decision.table.version == proposed.version + 1

    def test_a_no_with_nothing_standing_refuses_no_proposal(self):
        table = standing(3)

        decision = decide_refuse_to_abort(table, actor_at(table, 1))

        assert (decision.refusal, decision.table) == (Refusal.NO_PROPOSAL, table)

    def test_a_person_who_is_not_seated_refuses_not_seated(self):
        assert decide_refuse_to_abort(standing(3, voted=(1,)), newcomer()).refusal is Refusal.NOT_SEATED


class TestAChangeOfTheChairs:
    def test_the_freed_chair_of_a_voter_takes_its_yes(self):
        proposed = standing(3, voted=(1,))

        stood = decide_stand(proposed, actor_at(proposed, 1)).table

        assert (stood.progress.abort_yes, hand_runs(stood)) == (frozenset(), True)

    def test_a_stand_up_of_a_non_voter_completes_the_majority_in_its_version(self):
        proposed = standing(3, voted=(1,))

        stood = decide_stand(proposed, actor_at(proposed, 2)).table

        assert (is_aborted(stood), stood.version) == (True, proposed.version + 1)

    def test_a_send_away_of_a_non_voting_agent_completes_the_majority(self):
        proposed = with_agents(standing(3, voted=(1,)), 2)

        sent = decide_send_away(proposed, "account-rearhand").table

        assert (is_aborted(sent), sent.version) == (True, proposed.version + 1)

    def test_a_send_away_of_a_voting_agent_takes_its_yes_and_counts_again(self):
        proposed = sent_away(standing(3, voted=(2,)), 2)

        assert (proposed.progress.abort_yes, hand_runs(proposed)) == (frozenset(), True)

    def test_the_sit_that_leaves_no_chair_open_clears_the_proposal_and_the_hand_goes_on(self):
        proposed = standing(3, voted=(1,))

        sat = decide_sit(proposed, newcomer(), 3, None).table

        assert (sat.progress.abort_yes, hand_runs(sat), waiting_seat_of(sat)) == (frozenset(), True, None)

    def test_a_sit_while_another_chair_stays_open_keeps_the_proposal_and_the_newcomer_may_vote(self):
        proposed = standing(2, 3, voted=(1,))

        sat = decide_sit(proposed, newcomer(), 2, None).table
        ended = decide_agree_to_abort(sat, newcomer()).table

        assert (sat.progress.abort_yes, waiting_seat_of(sat)) == (frozenset({1}), 3)
        assert is_aborted(ended)


class TestAfterTheAbort:
    @pytest.fixture
    def aborted(self):
        series = Series(12, 3)
        entries = (an_entry(), an_entry())
        return agree(standing(2, 3, series=series, game_list=entries), 1).table

    def test_it_leaves_no_entry_no_result_and_no_step(self, aborted):
        assert (len(aborted.game_list), aborted.progress) == (2, HandProgress(aborted=True))
        assert result_pending(aborted) is False

    def test_it_counts_as_a_deal_of_the_series(self, aborted):
        assert (aborted.series.deals, series_games_left(aborted)) == (3, 9)

    def test_it_leaves_the_chairs_free_and_shows_it_as_aborted_with_no_next_dealer(self, aborted):
        view = view_of(aborted, "account-middlehand", NOBODY)

        assert (view.hand, view.passed_in, view.result) == (None, None, None)
        assert (view.aborted.next_dealer_seat, [chair.occupant_name for chair in view.chairs]) == (
            None,
            ["MIDDLEHAND", None, None],
        )

    def test_the_next_dealer_is_named_while_three_chairs_are_taken(self, aborted):
        full = replace(
            aborted,
            chairs=tuple(
                replace(chair, occupant=table_in(HandProgress()).chairs[chair.seat - 1].occupant)
                for chair in aborted.chairs
            ),
        )

        assert view_of(full, "account-middlehand", NOBODY).aborted.next_dealer_seat == 3

    def test_the_sit_of_the_third_deals_the_next_hand_at_once(self, aborted):
        two_seated = decide_sit(aborted, newcomer(name="Dora"), 2, None).table
        new_hand = NewHand(3, table_in(HandProgress()).hand)

        dealt = decide_sit(two_seated, newcomer(name="Eve"), 3, new_hand).table

        assert (hand_runs(dealt), dealt.dealer, dealt.progress, dealt.series.deals) == (True, 3, HandProgress(), 4)

    def test_three_connected_after_an_abort_are_due_without_a_tap(self, aborted):
        full = decide_sit(
            decide_sit(aborted, newcomer(name="Dora"), 2, None).table, newcomer(name="Eve"), 3, None
        ).table

        assert next_deal_due(full, frozenset({"account-middlehand", "account-dora", "account-eve"})) is True

    @pytest.mark.parametrize(
        ("rounds", "expected"),
        [
            pytest.param(ONE_BOCK_ROUND, BockRounds((2,)), id="uses-up-a-bock-game-and-adds-no-round"),
            pytest.param(BockRounds.start(), BockRounds.start(), id="no-rounds-stay-none"),
        ],
    )
    def test_it_uses_up_a_bock_game_and_fires_no_trigger_not_even_passed_in(self, rounds, expected):
        options = TableOptions(bock=BOCK_ON_EVERY_PASS)

        ended = agree(standing(2, 3, bock=rounds, options=options), 1).table

        assert ended.bock == expected

    def test_a_table_without_bock_holds_no_rounds(self, aborted):
        assert aborted.bock == BockRounds.start()

    def test_the_series_last_game_lapses_the_rounds_and_ends_the_series(self):
        last = standing(2, 3, series=Series(3, 3), bock=ONE_BOCK_ROUND, options=TableOptions(bock=BOCK_ON_EVERY_PASS))

        ended = agree(last, 1).table

        assert (ended.bock, series_over(ended)) == (BockRounds.start(), True)

    def test_an_aborted_ramsch_is_no_passed_in_hand(self):
        table = replace(table_in(HandProgress(auction=ALL_PASS), RAMSCH), chairs=standing(2, 3).chairs)

        view = view_of(agree(table, 1).table, "account-middlehand", NOBODY)

        assert (view.passed_in, view.aborted is not None) == (None, True)

    def test_a_seated_agent_votes_like_a_person(self):
        table = with_agents(standing(3), 1, 2)
        agent = actor_at(table, 1)

        assert agent.kind is OccupantKind.AGENT
        assert decide_agree_to_abort(table, agent).table.progress.abort_yes == frozenset({1})


class TestTheViews:
    def test_the_standing_proposal_is_the_same_seats_for_every_viewer(self):
        table = standing(3, voted=(2,))

        views = [
            view_of(table, account, NOBODY).hand for account in ("account-middlehand", "account-rearhand", "nobody")
        ]

        assert {(hand.abort, hand.abortable) for hand in views} == {((2,), True)}

    def test_no_proposal_and_no_open_chair_say_so(self):
        hand = view_of(standing(), "account-middlehand", NOBODY).hand

        assert (hand.abort, hand.abortable) == (None, False)


def test_the_payload_names_the_table_alone():
    assert abort_vote_payload(AbortVoteCommand("command-1", "table-1")) == "table-1"
