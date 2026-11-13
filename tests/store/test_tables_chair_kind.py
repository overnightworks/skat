from dataclasses import replace

import pytest

from skat.table.records import Actor, CreateTable, OccupantKind, SitDown, StandUp
from skat.table.service import TableService

pytestmark = pytest.mark.postgres

PERSON = Actor(account_id="account-anna", display_name="Anna")
AGENT = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)


def kinds_of(stored, transactions, table_id):
    return [
        None if chair.occupant is None else (chair.occupant.display_name, chair.occupant.kind)
        for chair in stored(transactions, table_id).chairs
    ]


class TestAChairKeepsItsOccupantsKind:
    def test_an_opener_and_a_sitter_keep_their_kind_and_name_for_a_new_service(self, service, transactions, stored):
        table_id = service.create(AGENT, CreateTable(command_id="command-open")).id
        service.sit(PERSON, SitDown(command_id="command-sit", table_id=table_id, seat=3), frozenset())

        restarted = TableService(transactions)

        assert kinds_of(stored, transactions, table_id) == [
            ("Mozart", OccupantKind.AGENT),
            None,
            ("Anna", OccupantKind.PERSON),
        ]
        assert restarted.view(PERSON, table_id, frozenset()).chairs[0].occupant_kind is OccupantKind.AGENT

    def test_a_chair_stood_from_has_no_kind_and_is_taken_again_with_the_next_sitters(
        self, service, transactions, stored
    ):
        table_id = service.create(AGENT, CreateTable(command_id="command-open")).id
        service.stand(AGENT, StandUp(command_id="command-stand", table_id=table_id), frozenset())
        assert kinds_of(stored, transactions, table_id)[0] is None

        service.sit(PERSON, SitDown(command_id="command-sit", table_id=table_id, seat=1), frozenset())

        assert kinds_of(stored, transactions, table_id)[0] == ("Anna", OccupantKind.PERSON)


class TestAChairKeepsItsAgentsOwner:
    def owners_of(self, stored, transactions, table_id):
        return [
            None if chair.occupant is None else chair.occupant.owner_account
            for chair in stored(transactions, table_id).chairs
        ]

    def test_an_opener_and_a_sitter_keep_their_owner_for_a_new_service(self, service, transactions, stored):
        owned = replace(AGENT, owner_account="account-felix")
        table_id = service.create(owned, CreateTable(command_id="command-open")).id
        service.sit(replace(owned, account_id="account-bach"), SitDown("command-sit", table_id, 2), frozenset())
        service.sit(PERSON, SitDown(command_id="command-anna", table_id=table_id, seat=3), frozenset())

        TableService(transactions)

        assert self.owners_of(stored, transactions, table_id) == ["account-felix", "account-felix", None]

    def test_the_owner_goes_with_the_chair_and_the_next_sitter_has_its_own(self, service, transactions, stored):
        owned = replace(AGENT, owner_account="account-felix")
        table_id = service.create(owned, CreateTable(command_id="command-open")).id
        service.stand(owned, StandUp(command_id="command-stand", table_id=table_id), frozenset())
        assert self.owners_of(stored, transactions, table_id)[0] is None

        service.sit(AGENT, SitDown(command_id="command-sit", table_id=table_id, seat=1), frozenset())

        assert self.owners_of(stored, transactions, table_id)[0] is None
