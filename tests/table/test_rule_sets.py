import itertools
from contextlib import contextmanager

import pytest

from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.table.records import Actor, RuleSetId, TableId, TableOptions
from skat.table.rule_sets import (
    RuleSet,
    RuleSetRefusal,
    RuleSetService,
    decide_save,
    ordered,
    rule_set_name,
)
from tests.support.fake_rule_sets import FakeRuleSetStore

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
EVENING = TableOptions(show_running_points=True)
KONTRA = TableOptions(kontra=KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD))


def a_set(number, name="Abend", options=EVENING, owner=ANNA.account_id):
    return RuleSet(RuleSetId(f"{number:032x}"), owner, name, options)


@pytest.fixture
def store():
    return FakeRuleSetStore()


@pytest.fixture
def service(store):
    numbers = itertools.count(1)
    return RuleSetService(store, new_rule_set_id=lambda: RuleSetId(f"{next(numbers):032x}"))


class TestName:
    @pytest.mark.parametrize(
        ("text", "name"),
        [
            ("Abend", "Abend"),
            ("  Abend \n", "Abend"),
            ("Café", "Café"),
            ("x" * 40, "x" * 40),
            ("a b", "a b"),
        ],
    )
    def test_a_name_is_stripped_and_in_composed_form(self, text, name):
        assert rule_set_name(text) == name

    @pytest.mark.parametrize("text", ["", "   ", "x" * 41, "Ab\x00end", "Ab\tend", "Ab\nend", "Ab\ud800end", "é" * 41])
    def test_a_text_that_is_no_name_is_refused(self, text):
        assert rule_set_name(text) is None

    def test_forty_decomposed_characters_that_compose_to_fewer_are_a_name(self):
        assert rule_set_name("é" * 40) == "é" * 40


class TestDecideSave:
    def test_a_new_name_is_saved_as_given(self):
        candidate = a_set(2, "Neu")

        assert decide_save([a_set(1)], candidate) == candidate

    def test_the_same_name_with_the_same_options_answers_the_held_set(self):
        assert decide_save([a_set(1)], a_set(2)) == a_set(1)

    def test_the_same_name_with_other_options_is_refused(self):
        assert decide_save([a_set(1)], a_set(2, options=KONTRA)) is RuleSetRefusal.NAME_TAKEN

    def test_a_name_differing_in_case_is_another_name(self):
        candidate = a_set(2, "abend")

        assert decide_save([a_set(1)], candidate) == candidate


class TestOrder:
    def test_sets_are_ordered_by_case_folded_name_then_id(self):
        sets = [a_set(3, "skatabend"), a_set(2, "Felix"), a_set(1, "Abend"), a_set(5, "felix"), a_set(4, "Felix ")]

        assert [(each.name, each.id.value[-1]) for each in ordered(sets)] == [
            ("Abend", "1"),
            ("Felix", "2"),
            ("felix", "5"),
            ("Felix ", "4"),
            ("skatabend", "3"),
        ]


class TestRuleSetId:
    def test_a_random_id_is_128_bits_of_hex_that_parses_back(self):
        identifiers = {RuleSetId.random() for _ in range(20)}

        assert len(identifiers) == 20
        assert all(RuleSetId.parse(each.value) == each for each in identifiers)

    @pytest.mark.parametrize("text", ["", "not-an-id", "A" * 32, "0" * 31, "0" * 33, "0" * 31 + "\x00"])
    def test_a_malformed_text_is_no_id(self, text):
        assert RuleSetId.parse(text) is None

    def test_ids_of_two_kinds_with_the_same_text_are_unequal(self):
        assert RuleSetId("0" * 32) != TableId("0" * 32)


class TestService:
    def test_a_saved_set_is_read_back_by_its_owner_only(self, service):
        saved = service.save(ANNA, "Abend", EVENING)

        assert service.sets(ANNA) == (saved,)
        assert service.sets(BEN) == ()

    def test_saving_again_with_the_same_options_changes_nothing(self, service, store):
        first = service.save(ANNA, "Abend", EVENING)

        assert service.save(ANNA, "Abend", EVENING) == first
        assert len(store.rule_sets) == 1

    def test_saving_a_taken_name_with_other_options_is_refused_and_keeps_the_set(self, service):
        first = service.save(ANNA, "Abend", EVENING)

        assert service.save(ANNA, "Abend", KONTRA) is RuleSetRefusal.NAME_TAKEN
        assert service.sets(ANNA) == (first,)

    def test_two_owners_may_hold_one_name(self, service):
        service.save(ANNA, "Abend", EVENING)
        bens = service.save(BEN, "Abend", KONTRA)

        assert isinstance(bens, RuleSet)
        assert service.sets(BEN) == (bens,)
        assert [each.options for each in service.sets(ANNA)] == [EVENING]

    def test_kontra_options_round_trip(self, service):
        service.save(ANNA, "Felix", KONTRA)

        assert service.sets(ANNA)[0].options == KONTRA

    def test_sets_come_ordered(self, service):
        for name in ("skatabend", "Felix", "Abend"):
            service.save(ANNA, name, EVENING)

        assert [each.name for each in service.sets(ANNA)] == ["Abend", "Felix", "skatabend"]

    def test_an_owner_deletes_a_set_once(self, service):
        saved = service.save(ANNA, "Abend", EVENING)

        assert service.delete(ANNA, saved.id.value) is True
        assert service.delete(ANNA, saved.id.value) is False
        assert service.sets(ANNA) == ()

    def test_another_account_deletes_nothing(self, service):
        saved = service.save(ANNA, "Abend", EVENING)

        assert service.delete(BEN, saved.id.value) is False
        assert service.sets(ANNA) == (saved,)

    @pytest.mark.parametrize("text", ["", "not-an-id", "0" * 31, "0" * 31 + "\x00", "0" * 32])
    def test_a_malformed_or_unknown_id_deletes_nothing(self, service, text):
        saved = service.save(ANNA, "Abend", EVENING)

        assert service.delete(ANNA, text) is False
        assert service.sets(ANNA) == (saved,)


class RacingStore(FakeRuleSetStore):
    """Another request commits the rival set between the first read of the saving transaction and its write."""

    def __init__(self, rival):
        super().__init__()
        self._rival = rival
        self._committed = []

    @contextmanager
    def begin(self):
        try:
            with super().begin() as transaction:
                yield transaction
        finally:
            # The rival's commit stands when this transaction rolls back.
            for rival in self._committed:
                self.rule_sets[rival.id.value] = rival

    def sets_of(self, owner_account):
        owned = super().sets_of(owner_account)
        if self._rival is not None and owner_account == self._rival.owner_account:
            self.rule_sets[self._rival.id.value] = self._rival
            self._committed.append(self._rival)
            self._rival = None
        return owned


class TestConcurrentSave:
    @pytest.fixture
    def racing(self):
        def build(rival):
            numbers = itertools.count(10)
            return RuleSetService(RacingStore(rival), new_rule_set_id=lambda: RuleSetId(f"{next(numbers):032x}"))

        return build

    def test_the_loser_with_other_options_is_refused_name_taken(self, racing):
        assert racing(a_set(1, options=KONTRA)).save(ANNA, "Abend", EVENING) is RuleSetRefusal.NAME_TAKEN

    def test_the_loser_with_the_same_options_answers_the_winner(self, racing):
        assert racing(a_set(1)).save(ANNA, "Abend", EVENING) == a_set(1)
