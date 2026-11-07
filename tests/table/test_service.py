import itertools

import pytest

from skat.table.records import Actor, CreateTable, Receipt, TableId
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

        view = service.view(VISITOR, created.id)

        assert [(chair.seat, chair.occupant_name, chair.is_mine) for chair in view.chairs] == [
            (1, "Anna", False),
            (2, None, False),
            (3, None, False),
        ]

    def test_shows_the_opener_their_own_chair_after_a_reload(self, service):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        assert service.view(OPENER, created.id) == created

    @pytest.mark.parametrize("table_id", ["0" * 32, "", "not-an-id", "A" * 32, "0" * 31, "0" * 33, "../" + "0" * 29])
    def test_an_unknown_or_malformed_id_is_no_table(self, service, table_id):
        assert service.view(OPENER, table_id) is None


class TestTableId:
    def test_a_random_id_is_128_bits_of_hex_that_parses_back(self):
        identifiers = {TableId.random() for _ in range(50)}

        assert len(identifiers) == 50
        assert all(
            len(identifier.value) == 32 and TableId.parse(identifier.value) == identifier for identifier in identifiers
        )
