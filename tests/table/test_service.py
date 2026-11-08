import itertools

import pytest

from skat.table.records import Actor, CreateTable, Receipt, Refusal, SitDown, StandUp, TableId
from skat.table.service import CommandIdReusedError, TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.faulty_tables import FaultyTableTransactions

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")


@pytest.fixture
def store():
    return FakeTableStore()


@pytest.fixture
def service(store):
    numbers = itertools.count(1)
    return TableService(store, new_table_id=lambda: TableId(f"{next(numbers):032x}"))


class TestCreate:
    def test_seats_the_opener_in_chair_one_with_two_free_chairs(self, service):
        view = service.create(OPENER, CreateTable(command_id="command-1"))

        assert [(chair.seat, chair.occupant_name, chair.is_mine) for chair in view.chairs] == [
            (1, "Anna", True),
            (2, None, False),
            (3, None, False),
        ]

    def test_starts_the_table_at_version_one(self, service):
        assert service.create(OPENER, CreateTable(command_id="command-1")).version == 1

    def test_one_account_may_open_any_number_of_tables(self, service, store):
        first = service.create(OPENER, CreateTable(command_id="command-1"))
        second = service.create(OPENER, CreateTable(command_id="command-2"))

        assert first.id != second.id
        assert len(store.tables) == 2

    def test_the_same_command_id_and_payload_returns_the_table_the_first_request_created(self, service, store):
        first = service.create(OPENER, CreateTable(command_id="command-1"))
        again = service.create(OPENER, CreateTable(command_id="command-1"))

        assert again == first
        assert len(store.tables) == 1

    def test_another_account_using_the_same_command_id_opens_its_own_table(self, service, store):
        service.create(OPENER, CreateTable(command_id="command-1"))
        service.create(VISITOR, CreateTable(command_id="command-1"))

        assert len(store.tables) == 2

    def test_a_command_id_reused_with_another_payload_is_refused_and_writes_nothing(self, service, store):
        first = service.create(OPENER, CreateTable(command_id="command-1"))
        receipt = store.receipts[(OPENER.account_id, "command-1")]
        store.receipts[(OPENER.account_id, "command-1")] = Receipt(
            receipt.account_id, receipt.command_id, receipt.command, '{"seats": 4}', receipt.table_id
        )

        command = CreateTable(command_id="command-1")

        with pytest.raises(CommandIdReusedError):
            service.create(OPENER, command)

        assert list(store.tables) == [first.id]

    def test_a_failure_between_the_table_write_and_the_receipt_persists_nothing(self, service, store):
        faulty = TableService(FaultyTableTransactions(store, receipt_failure=RuntimeError("connection lost")))

        command = CreateTable(command_id="command-1")

        with pytest.raises(RuntimeError, match="connection lost"):
            faulty.create(OPENER, command)

        assert (store.tables, store.receipts) == ({}, {})

    def test_loses_a_race_against_an_identical_request_by_returning_the_winners_table(self, service, store):
        winner = service.create(OPENER, CreateTable(command_id="command-1"))
        blind = TableService(FaultyTableTransactions(store, blind_first_replay=True))

        assert blind.create(OPENER, CreateTable(command_id="command-1")) == winner
        assert len(store.tables) == 1


class TestView:
    def test_shows_another_member_the_opener_in_chair_one_and_assigns_them_no_chair(self, service):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        view = service.view(VISITOR, created.id, frozenset())

        assert [(chair.seat, chair.occupant_name, chair.is_mine) for chair in view.chairs] == [
            (1, "Anna", False),
            (2, None, False),
            (3, None, False),
        ]

    def test_shows_the_opener_their_own_chair_after_a_reload(self, service):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        assert service.view(OPENER, created.id, frozenset()) == created

    @pytest.mark.parametrize(
        ("connected", "watchers"),
        [
            pytest.param(frozenset(), 0, id="nobody-connected"),
            pytest.param({OPENER.account_id}, 0, id="the-seated-opener-is-no-watcher"),
            pytest.param({VISITOR.account_id}, 1, id="a-connected-member-without-a-chair-watches"),
            pytest.param({OPENER.account_id, VISITOR.account_id, "account-third"}, 2, id="each-account-counts-once"),
        ],
    )
    def test_counts_the_connected_members_without_a_chair_as_watchers(self, service, connected, watchers):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        assert service.view(VISITOR, created.id, connected).watchers == watchers

    def test_a_new_table_has_no_watchers(self, service):
        assert service.create(OPENER, CreateTable(command_id="command-1")).watchers == 0

    @pytest.mark.parametrize("table_id", ["0" * 32, "", "not-an-id", "A" * 32, "0" * 31, "0" * 33, "../" + "0" * 29])
    def test_an_unknown_or_malformed_id_is_no_table(self, service, table_id):
        assert service.view(OPENER, table_id, frozenset()) is None


class TestTableId:
    def test_a_random_id_is_128_bits_of_hex_that_parses_back(self):
        identifiers = {TableId.random() for _ in range(50)}

        assert len(identifiers) == 50
        assert all(
            len(identifier.value) == 32 and TableId.parse(identifier.value) == identifier for identifier in identifiers
        )


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-open")).id


def sit(service, actor, table_id, seat, command_id="command-sit"):
    return service.sit(actor, SitDown(command_id, table_id, seat))


def occupants_of(view):
    return [chair.occupant_name for chair in view.chairs]


class TestSit:
    def test_seats_the_member_in_the_chair_and_marks_it_theirs(self, service, table_id):
        result = sit(service, VISITOR, table_id, 2)

        assert result.refusal is None
        assert [(chair.occupant_name, chair.is_mine) for chair in result.view.chairs] == [
            ("Anna", False),
            ("Ben", True),
            (None, False),
        ]

    def test_the_seat_is_there_for_the_next_read(self, service, table_id):
        sit(service, VISITOR, table_id, 2)

        assert occupants_of(service.view(OPENER, table_id, frozenset())) == ["Anna", "Ben", None]

    def test_refuses_a_taken_chair_naming_who_holds_it(self, service, table_id):
        result = sit(service, VISITOR, table_id, 1)

        assert (result.refusal, result.holder) == (Refusal.SEAT_TAKEN, "Anna")
        assert occupants_of(result.view) == ["Anna", None, None]

    def test_the_loser_of_the_last_chair_is_told_who_got_it(self, service, table_id):
        sit(service, VISITOR, table_id, 2)
        sit(service, Actor("account-third", "Cem"), table_id, 3)

        late = sit(service, Actor("account-fourth", "Dora"), table_id, 3)

        assert (late.refusal, late.holder) == (Refusal.SEAT_TAKEN, "Cem")

    def test_refuses_a_second_chair_to_a_seated_member(self, service, table_id):
        result = sit(service, OPENER, table_id, 2)

        assert result.refusal is Refusal.ALREADY_SEATED
        assert occupants_of(result.view) == ["Anna", None, None]

    def test_a_retry_returns_the_first_seat_and_writes_nothing_more(self, service, store, table_id):
        first = sit(service, VISITOR, table_id, 2)
        written = dict(store.tables)

        assert sit(service, VISITOR, table_id, 2) == first
        assert store.tables == written

    def test_a_retry_of_a_refusal_returns_the_refusal_even_after_the_chair_frees_up(self, service, table_id):
        first = sit(service, VISITOR, table_id, 1)
        service.stand(OPENER, StandUp("command-stand", table_id))

        again = sit(service, VISITOR, table_id, 1)

        assert (again.refusal, again.holder) == (first.refusal, first.holder)
        assert occupants_of(again.view) == [None, None, None]

    def test_refuses_a_command_id_reused_for_another_chair(self, service, store, table_id):
        sit(service, VISITOR, table_id, 2)
        before = dict(store.tables)

        with pytest.raises(CommandIdReusedError):
            sit(service, VISITOR, table_id, 3)

        assert store.tables == before

    def test_refuses_a_command_id_reused_by_stand_up(self, service, table_id):
        sit(service, VISITOR, table_id, 2)

        reuse = StandUp("command-sit", table_id)

        with pytest.raises(CommandIdReusedError):
            service.stand(VISITOR, reuse)

    @pytest.mark.parametrize("unknown", ["0" * 32, "", "not-an-id"])
    def test_an_unknown_or_malformed_table_is_no_table_and_writes_nothing(self, service, store, unknown):
        before = (dict(store.tables), dict(store.receipts))

        assert sit(service, VISITOR, unknown, 2) is None
        assert (store.tables, store.receipts) == before

    def test_a_failure_after_the_decision_persists_nothing(self, store, table_id):
        before = (dict(store.tables), dict(store.receipts))
        faulty = TableService(FaultyTableTransactions(store, receipt_failure=RuntimeError("connection lost")))

        with pytest.raises(RuntimeError, match="connection lost"):
            sit(faulty, VISITOR, table_id, 2)

        assert (store.tables, store.receipts) == before

    def test_the_same_command_id_on_another_table_is_refused_when_it_races_the_first(self, service, store, table_id):
        other_id = service.create(OPENER, CreateTable(command_id="command-other")).id
        sit(service, VISITOR, table_id, 2)
        blind = TableService(FaultyTableTransactions(store, blind_first_replay=True))

        with pytest.raises(CommandIdReusedError):
            sit(blind, VISITOR, other_id, 2)


class TestStand:
    def test_frees_the_own_chair_and_keeps_every_number(self, service, table_id):
        sit(service, VISITOR, table_id, 3)

        result = service.stand(VISITOR, StandUp("command-stand", table_id))

        assert result.refusal is None
        assert [(chair.seat, chair.occupant_name) for chair in result.view.chairs] == [
            (1, "Anna"),
            (2, None),
            (3, None),
        ]

    def test_refuses_a_member_without_a_chair_and_changes_nothing(self, service, table_id):
        result = service.stand(VISITOR, StandUp("command-stand", table_id))

        assert result.refusal is Refusal.NOT_SEATED
        assert occupants_of(service.view(OPENER, table_id, frozenset())) == ["Anna", None, None]

    def test_a_retry_returns_the_first_outcome(self, service, store, table_id):
        first = service.stand(OPENER, StandUp("command-stand", table_id))
        written = dict(store.tables)

        assert service.stand(OPENER, StandUp("command-stand", table_id)) == first
        assert store.tables == written

    def test_another_member_may_take_the_freed_chair(self, service, table_id):
        service.stand(OPENER, StandUp("command-stand", table_id))

        assert occupants_of(sit(service, VISITOR, table_id, 1).view) == ["Ben", None, None]

    def test_an_unknown_table_is_no_table(self, service):
        assert service.stand(OPENER, StandUp("command-stand", "0" * 32)) is None
