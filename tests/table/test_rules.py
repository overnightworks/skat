import random
from dataclasses import replace

import pytest

from skat.engine.deal import deal
from skat.table.records import Actor, Chair, FirstDeal, Occupant, Refusal, TableId, TableRecord
from skat.table.rules import decide_sit, decide_stand, hand_runs, sit_deals

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
DRAWN = FirstDeal(dealer=2, hand=deal(random.Random(3)))  # noqa: S311 - a seeded source makes the deal reproducible


def table_with(*seated: tuple[int, Actor]) -> TableRecord:
    occupants = {seat: Occupant(actor.account_id, actor.display_name) for seat, actor in seated}
    return TableRecord(TableId("0" * 32), 4, tuple(Chair(seat, occupants.get(seat)) for seat in (1, 2, 3)))


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

    @pytest.mark.parametrize("seated", [[(1, ANNA)], [(1, ANNA), (3, BEN)]])
    def test_a_sit_that_leaves_a_chair_free_deals_nothing(self, seated):
        free = next(seat for seat in (1, 2, 3) if seat not in dict(seated))

        decision = decide_sit(table_with(*seated), CLEO, free, None)

        assert (decision.table.dealer, decision.table.hand) == (None, None)

    def test_a_sit_while_a_hand_runs_is_seat_taken_and_deals_nothing_more(self):
        table = running_hand()

        decision = decide_sit(table, DORA, 2, FirstDeal(dealer=3, hand=deal(random.Random(4))))  # noqa: S311

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
