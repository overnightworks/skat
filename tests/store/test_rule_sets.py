import threading
from contextlib import contextmanager

import pytest

from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.store.rule_sets import PostgresRuleSets
from skat.table.records import Actor, RuleSetId, TableOptions
from skat.table.rule_sets import DuplicateRuleSetError, RuleSet, RuleSetRefusal, RuleSetService

pytestmark = pytest.mark.postgres

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
EVENING = TableOptions(show_running_points=True)
FELIX = TableOptions(kontra=KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD))
RACE_SECONDS = 10


@pytest.fixture
def rule_sets(engine):
    return PostgresRuleSets(engine)


@pytest.fixture
def service(rule_sets):
    return RuleSetService(rule_sets)


def a_set(name="Abend", options=EVENING, owner=ANNA.account_id):
    return RuleSet(RuleSetId.random(), owner, name, options)


class TestStoredOptions:
    @pytest.mark.parametrize("options", [TableOptions(), EVENING, FELIX, TableOptions(True, FELIX.kontra)])
    def test_the_options_of_a_set_read_back_as_saved(self, service, options):
        saved = service.save(ANNA, "Satz", options)

        assert service.sets(ANNA) == (saved,)
        assert saved.options == options

    def test_a_new_service_over_the_same_database_reads_the_same_sets(self, engine, service):
        saved = service.save(ANNA, "Abend", FELIX)

        assert RuleSetService(PostgresRuleSets(engine)).sets(ANNA) == (saved,)


class TestOwnership:
    def test_one_owner_may_not_hold_a_name_twice(self, rule_sets):
        with rule_sets.begin() as transaction:
            transaction.add(a_set())

        with pytest.raises(DuplicateRuleSetError), rule_sets.begin() as transaction:
            transaction.add(a_set())

    def test_two_owners_may_hold_one_name_each_with_its_own_id(self, service):
        annas = service.save(ANNA, "Abend", EVENING)
        bens = service.save(BEN, "Abend", FELIX)

        assert (annas.id, bens.id) == (service.sets(ANNA)[0].id, service.sets(BEN)[0].id)
        assert annas.id != bens.id
        assert (service.sets(ANNA)[0].options, service.sets(BEN)[0].options) == (EVENING, FELIX)

    def test_an_account_deletes_only_its_own_set(self, service):
        annas = service.save(ANNA, "Abend", EVENING)

        assert service.delete(BEN, annas.id.value) is False
        assert service.sets(ANNA) == (annas,)
        assert service.delete(ANNA, annas.id.value) is True
        assert service.sets(ANNA) == ()

    def test_a_delete_with_a_nul_byte_in_the_id_touches_no_row(self, service):
        saved = service.save(ANNA, "Abend", EVENING)

        assert service.delete(ANNA, "0" * 31 + "\x00") is False
        assert service.sets(ANNA) == (saved,)


class _MeetingRuleSets:
    """The store, where each transaction waits after its first read until the other has read too."""

    def __init__(self, inner, parties):
        self._inner = inner
        self._barrier = threading.Barrier(parties, timeout=RACE_SECONDS)
        self._met = threading.local()

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            yield _Meeting(transaction, self._barrier, self._met)


class _Meeting:
    def __init__(self, inner, barrier, met):
        self._inner = inner
        self._barrier = barrier
        self._met = met

    def sets_of(self, owner_account):
        owned = self._inner.sets_of(owner_account)
        if not getattr(self._met, "done", False):
            self._met.done = True
            self._barrier.wait()
        return owned

    def add(self, rule_set):
        self._inner.add(rule_set)

    def delete(self, owner_account, rule_set_id):
        return self._inner.delete(owner_account, rule_set_id)


class TestConcurrentSaves:
    def test_of_two_saves_of_one_new_name_with_other_options_one_is_stored_and_the_other_refused(self, rule_sets):
        service = RuleSetService(_MeetingRuleSets(rule_sets, 2))
        answers = []

        def save(options):
            answers.append(service.save(ANNA, "Abend", options))

        racers = [threading.Thread(target=save, args=(options,)) for options in (EVENING, FELIX)]
        for racer in racers:
            racer.start()
        for racer in racers:
            racer.join(RACE_SECONDS)

        stored = RuleSetService(rule_sets).sets(ANNA)
        assert len(stored) == 1
        assert RuleSetRefusal.NAME_TAKEN in answers
        assert stored[0] in answers
