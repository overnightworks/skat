import pytest

from skat.table.records import Actor, Chair, Occupant, Refusal, TableId, TableRecord
from skat.table.rules import decide_sit, decide_stand

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")


def table_with(*seated: tuple[int, Actor]) -> TableRecord:
    occupants = {seat: Occupant(actor.account_id, actor.display_name) for seat, actor in seated}
    return TableRecord(TableId("0" * 32), 4, tuple(Chair(seat, occupants.get(seat)) for seat in (1, 2, 3)))


def occupants_of(table: TableRecord) -> list[str | None]:
    return [None if chair.occupant is None else chair.occupant.display_name for chair in table.chairs]


class TestSit:
    def test_seats_a_member_in_a_free_chair_and_bumps_the_version(self):
        decision = decide_sit(table_with((1, ANNA)), BEN, 3)

        assert decision.refusal is None
        assert occupants_of(decision.table) == ["Anna", None, "Ben"]
        assert decision.table.version == 5

    def test_refuses_a_taken_chair_and_names_who_holds_it(self):
        table = table_with((2, ANNA))

        decision = decide_sit(table, BEN, 2)

        assert (decision.refusal, decision.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert decision.table == table

    def test_refuses_a_second_chair_to_a_seated_member(self):
        table = table_with((1, ANNA))

        decision = decide_sit(table, ANNA, 2)

        assert decision.refusal is Refusal.ALREADY_SEATED
        assert decision.table == table

    def test_refuses_the_own_chair_as_taken(self):
        assert decide_sit(table_with((1, ANNA)), ANNA, 1).refusal is Refusal.ALREADY_SEATED

    def test_keeps_every_chair_number(self):
        decision = decide_sit(table_with((1, ANNA)), BEN, 2)

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

        assert occupants_of(decide_sit(stood, BEN, seat).table)[seat - 1] == "Ben"
