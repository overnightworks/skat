import random
from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.deal import Position, deal
from skat.table.records import Actor, Chair, HandProgress, NewHand, Occupant, Refusal, TableId, TableRecord
from skat.table.rules import (
    dealt_next,
    decide_free_chair,
    decide_sit,
    decide_stand,
    hand_runs,
    next_deal_due,
    result_pending,
    sit_deals,
)
from tests.support.played_game import an_entry

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
DRAWN = NewHand(dealer=2, hand=deal(random.Random(3)))  # noqa: S311 - a seeded source makes the deal reproducible


def table_with(*seated: tuple[int, Actor]) -> TableRecord:
    occupants = {seat: Occupant(actor.account_id, actor.display_name) for seat, actor in seated}
    return TableRecord(
        TableId("0" * 32),
        4,
        tuple(Chair(seat, occupants.get(seat)) for seat in (1, 2, 3)),
        dealer=None,
        hand=None,
        progress=HandProgress(),
        game_list=(),
    )


def occupants_of(table: TableRecord) -> list[str | None]:
    return [None if chair.occupant is None else chair.occupant.display_name for chair in table.chairs]


class TestSit:
    def test_seats_a_member_in_a_free_chair_and_bumps_the_version(self):
        decision = decide_sit(table_with((1, ANNA)), BEN, 3, None)

        assert decision.refusal is None
        assert occupants_of(decision.table) == ["Anna", None, "Ben"]
        assert decision.table.version == 5

    def test_refuses_a_taken_chair_and_names_who_holds_it(self):
        table = table_with((2, ANNA))

        decision = decide_sit(table, BEN, 2, None)

        assert (decision.refusal, decision.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert decision.table == table

    def test_refuses_a_second_chair_to_a_seated_member(self):
        table = table_with((1, ANNA))

        decision = decide_sit(table, ANNA, 2, None)

        assert decision.refusal is Refusal.ALREADY_SEATED
        assert decision.table == table

    def test_refuses_the_own_chair_as_taken(self):
        assert decide_sit(table_with((1, ANNA)), ANNA, 1, None).refusal is Refusal.ALREADY_SEATED

    def test_keeps_every_chair_number(self):
        decision = decide_sit(table_with((1, ANNA)), BEN, 2, None)

        assert [chair.seat for chair in decision.table.chairs] == [1, 2, 3]


class TestStand:
    def test_clears_only_the_own_chair_and_bumps_the_version(self):
        decision = decide_stand(table_with((1, ANNA), (2, BEN)), BEN)

        assert decision.refusal is None
        assert occupants_of(decision.table) == ["Anna", None, None]
        assert decision.table.version == 5

    def test_refuses_a_member_without_a_chair(self):
        table = table_with((1, ANNA))

        decision = decide_stand(table, BEN)

        assert decision.refusal is Refusal.NOT_SEATED
        assert decision.table == table

    @pytest.mark.parametrize("seat", [1, 2, 3])
    def test_a_chair_stood_from_keeps_its_number_for_the_next_to_sit(self, seat):
        stood = decide_stand(table_with((seat, ANNA)), ANNA).table

        assert occupants_of(decide_sit(stood, BEN, seat, None).table)[seat - 1] == "Ben"


def running_hand() -> TableRecord:
    return replace(table_with((1, ANNA), (2, BEN), (3, CLEO)), dealer=DRAWN.dealer, hand=DRAWN.hand)


class TestDeal:
    @pytest.mark.parametrize("last_free", [1, 2, 3])
    def test_the_sit_in_the_last_free_chair_deals_the_drawn_hand_and_dealer_in_one_version_bump(self, last_free):
        others = [(seat, actor) for seat, actor in ((1, ANNA), (2, BEN), (3, CLEO)) if seat != last_free]
        table = table_with(*others)

        decision = decide_sit(table, DORA, last_free, DRAWN)

        assert decision.refusal is None
        assert (decision.table.dealer, decision.table.hand) == (DRAWN.dealer, DRAWN.hand)
        assert all(chair.occupant is not None for chair in decision.table.chairs)
        assert decision.table.version == table.version + 1

    def test_the_sit_that_deals_after_a_passed_in_hand_replaces_the_hand_and_empties_the_auction_in_one_bump(self):
        steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
        table = replace(table_with((1, ANNA), (2, BEN)), dealer=1, progress=HandProgress(steps))

        decision = decide_sit(table, CLEO, 3, DRAWN)

        assert (decision.table.dealer, decision.table.hand) == (DRAWN.dealer, DRAWN.hand)
        assert decision.table.progress == HandProgress()
        assert decision.table.version == table.version + 1

    @pytest.mark.parametrize("seated", [[], [(1, ANNA)]])
    def test_a_sit_that_leaves_a_chair_free_deals_nothing(self, seated):
        free = next(seat for seat in (1, 2, 3) if seat not in dict(seated))

        decision = decide_sit(table_with(*seated), CLEO, free, None)

        assert (decision.table.dealer, decision.table.hand) == (None, None)

    def test_a_sit_while_a_hand_runs_is_seat_taken_and_deals_nothing_more(self):
        table = running_hand()

        decision = decide_sit(table, DORA, 2, NewHand(dealer=3, hand=deal(random.Random(4))))  # noqa: S311 - a seeded source makes the deal reproducible

        assert (decision.refusal, decision.holder) == (Refusal.SEAT_TAKEN, "Ben")
        assert decision.table == table

    @pytest.mark.parametrize(
        ("table", "deals"),
        [
            pytest.param(table_with((1, ANNA)), False, id="two-chairs-free"),
            pytest.param(table_with((1, ANNA), (2, BEN)), True, id="one-chair-free"),
            pytest.param(running_hand(), False, id="a-hand-runs"),
        ],
    )
    def test_a_sit_deals_when_it_fills_the_last_free_chair_and_no_hand_runs(self, table, deals):
        assert sit_deals(table) is deals

    def test_a_hand_runs_while_the_table_holds_one_and_not_without(self):
        assert hand_runs(running_hand()) is True
        assert hand_runs(table_with((1, ANNA), (2, BEN))) is False

    @pytest.mark.parametrize("member", [ANNA, BEN, CLEO])
    def test_no_seated_member_stands_up_while_a_hand_runs(self, member):
        table = running_hand()

        decision = decide_stand(table, member)

        assert decision.refusal is Refusal.HAND_RUNNING
        assert decision.table == table

    def test_a_member_without_a_chair_is_not_seated_even_while_a_hand_runs(self):
        assert decide_stand(running_hand(), DORA).refusal is Refusal.NOT_SEATED


class TestFreeChair:
    def test_frees_only_the_away_members_chair_keeps_every_number_and_bumps_the_version(self):
        decision = decide_free_chair(table_with((1, ANNA), (2, BEN)), BEN.account_id)

        assert decision.refusal is None
        assert occupants_of(decision.table) == ["Anna", None, None]
        assert [chair.seat for chair in decision.table.chairs] == [1, 2, 3]
        assert decision.table.version == 5

    def test_changes_nothing_for_a_member_who_no_longer_holds_a_chair(self):
        table = table_with((1, ANNA))

        decision = decide_free_chair(table, BEN.account_id)

        assert decision.refusal is Refusal.NOT_SEATED
        assert decision.table == table

    @pytest.mark.parametrize("member", [ANNA, BEN, CLEO])
    def test_changes_nothing_while_a_hand_runs(self, member):
        table = running_hand()

        decision = decide_free_chair(table, member.account_id)

        assert decision.refusal is Refusal.HAND_RUNNING
        assert decision.table == table


ALL_THREE = frozenset({ANNA.account_id, BEN.account_id, CLEO.account_id})


def passed_in() -> TableRecord:
    steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
    return replace(table_with((1, ANNA), (2, BEN), (3, CLEO)), dealer=2, progress=HandProgress(steps))


def played_out() -> TableRecord:
    """The record the thirtieth card leaves: no hand, no steps, the dealer and one entry."""
    return replace(table_with((1, ANNA), (2, BEN), (3, CLEO)), dealer=2, game_list=(an_entry(),))


class TestResultPending:
    @pytest.mark.parametrize(
        ("table", "pending"),
        [
            pytest.param(played_out(), True, id="a-played-game"),
            pytest.param(replace(passed_in(), game_list=(an_entry(),)), False, id="a-pass-in-after-a-played-game"),
            pytest.param(passed_in(), False, id="a-pass-in-alone"),
            pytest.param(replace(running_hand(), game_list=(an_entry(),)), False, id="a-hand-runs"),
            pytest.param(replace(played_out(), dealer=None), False, id="no-dealer"),
            pytest.param(replace(played_out(), game_list=()), False, id="no-entry"),
        ],
    )
    def test_holds_with_no_hand_a_dealer_an_entry_and_no_auction_steps(self, table, pending):
        assert result_pending(table) is pending

    def test_a_seated_member_stands_up_and_the_list_stays(self):
        table = played_out()

        decision = decide_stand(table, BEN)

        assert decision.refusal is None
        assert occupants_of(decision.table) == [ANNA.display_name, None, CLEO.display_name]
        assert decision.table.game_list == table.game_list


class TestNextDeal:
    @pytest.mark.parametrize(
        ("table", "connected", "due"),
        [
            pytest.param(passed_in(), ALL_THREE, True, id="all-three-connected"),
            pytest.param(played_out(), ALL_THREE, False, id="a-result-pending"),
            pytest.param(
                replace(passed_in(), game_list=(an_entry(),)), ALL_THREE, True, id="a-pass-in-after-a-played-game"
            ),
            pytest.param(passed_in(), ALL_THREE | {DORA.account_id}, True, id="a-watcher-as-well"),
            pytest.param(passed_in(), ALL_THREE - {CLEO.account_id}, False, id="one-member-away"),
            pytest.param(
                replace(passed_in(), chairs=table_with((1, ANNA), (2, BEN)).chairs), ALL_THREE, False, id="a-chair-free"
            ),
            pytest.param(running_hand(), ALL_THREE, False, id="a-hand-runs"),
            pytest.param(replace(passed_in(), dealer=None), ALL_THREE, False, id="never-dealt"),
        ],
    )
    def test_is_due_only_when_no_hand_runs_a_dealer_exists_and_all_three_occupants_are_connected(
        self, table, connected, due
    ):
        assert next_deal_due(table, connected) is due

    def test_the_next_hand_replaces_the_cards_and_steps_keeps_the_chairs_and_bumps_the_version_once(self):
        table = passed_in()

        next_hand = dealt_next(table, DRAWN)

        assert (next_hand.dealer, next_hand.hand, next_hand.progress) == (DRAWN.dealer, DRAWN.hand, HandProgress())
        assert next_hand.chairs == table.chairs
        assert next_hand.version == table.version + 1

    def test_the_next_hand_keeps_the_game_list(self):
        table = replace(passed_in(), game_list=(an_entry(),))

        assert dealt_next(table, DRAWN).game_list == table.game_list


def ready_at(table: TableRecord, *seats: int) -> TableRecord:
    return replace(table, chairs=tuple(replace(chair, ready=chair.seat in seats) for chair in table.chairs))


def ready_seats(table: TableRecord) -> list[int]:
    return [chair.seat for chair in table.chairs if chair.ready]


class TestNextDealAfterAResult:
    @pytest.mark.parametrize(
        ("table", "connected", "due"),
        [
            pytest.param(ready_at(played_out(), 1, 2, 3), ALL_THREE, True, id="all-three-ready-and-connected"),
            pytest.param(ready_at(played_out(), 1, 2), ALL_THREE, False, id="one-not-ready"),
            pytest.param(played_out(), ALL_THREE, False, id="nobody-ready"),
            pytest.param(ready_at(played_out(), 1, 2, 3), ALL_THREE - {BEN.account_id}, False, id="all-ready-one-away"),
            pytest.param(
                replace(ready_at(played_out(), 1, 3), chairs=ready_at(table_with((1, ANNA), (3, CLEO)), 1, 3).chairs),
                ALL_THREE,
                False,
                id="a-chair-free",
            ),
        ],
    )
    def test_is_due_only_with_all_three_ready_and_connected(self, table, connected, due):
        assert next_deal_due(table, connected) is due

    def test_a_passed_in_hand_needs_no_mark(self):
        assert next_deal_due(replace(passed_in(), game_list=(an_entry(),)), ALL_THREE) is True

    def test_the_next_hand_clears_every_mark(self):
        assert ready_seats(dealt_next(ready_at(played_out(), 1, 2, 3), DRAWN)) == []

    def test_the_sit_that_deals_clears_every_mark(self):
        table = ready_at(table_with((1, ANNA), (2, BEN)), 1, 2)

        decision = decide_sit(table, CLEO, 3, DRAWN)

        assert decision.table.hand == DRAWN.hand
        assert ready_seats(decision.table) == []


def a_free_chair_during_a_result(*ready: int) -> TableRecord:
    return replace(played_out(), chairs=ready_at(table_with((1, ANNA), (2, BEN)), *ready).chairs)


class TestSitDuringAResult:
    def test_no_sit_deals_while_a_result_is_pending(self):
        assert sit_deals(a_free_chair_during_a_result()) is False

    def test_the_sitter_counts_as_ready_and_the_others_keep_their_marks(self):
        decision = decide_sit(a_free_chair_during_a_result(1), DORA, 3, None)

        assert decision.refusal is None
        assert (decision.table.hand, ready_seats(decision.table)) == (None, [1, 3])
        assert decision.table.version == played_out().version + 1

    def test_a_sit_outside_a_result_sets_no_mark(self):
        decision = decide_sit(table_with((1, ANNA)), BEN, 2, None)

        assert ready_seats(decision.table) == []


class TestLeavingClearsOnlyTheOwnMark:
    def test_standing_up_frees_the_chair_and_its_mark_and_keeps_the_others(self):
        decision = decide_stand(ready_at(played_out(), 1, 2, 3), ANNA)

        assert occupants_of(decision.table)[0] is None
        assert ready_seats(decision.table) == [2, 3]

    def test_the_server_freeing_an_away_members_chair_clears_its_mark(self):
        decision = decide_free_chair(ready_at(played_out(), 1, 2), ANNA.account_id)

        assert occupants_of(decision.table)[0] is None
        assert ready_seats(decision.table) == [2]
