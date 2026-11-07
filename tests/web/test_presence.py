import itertools

import pytest

from skat.table.records import Actor, CreateTable, TableId
from skat.table.service import TableService
from skat.web.presence import Presence
from tests.support.fake_tables import FakeTableStore

TABLE = "t" * 32
OTHER_TABLE = "o" * 32


class Wakes:
    """What each subscriber was told: one counter per name."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def callback(self, name):
        self.counts.setdefault(name, 0)

        def wake():
            self.counts[name] += 1

        return wake


@pytest.fixture
def wakes():
    return Wakes()


@pytest.fixture
def presence():
    return Presence()


class TestConnectedAccounts:
    def test_nobody_is_connected_to_a_table_nobody_opened(self, presence):
        assert presence.connected(TABLE) == frozenset()

    def test_an_account_in_two_tabs_is_connected_once_until_its_last_tab_closes(self, presence, wakes):
        first = presence.subscribe(TABLE, "anna", wakes.callback("first"))
        second = presence.subscribe(TABLE, "anna", wakes.callback("second"))

        presence.unsubscribe(first)
        assert presence.connected(TABLE) == {"anna"}
        presence.unsubscribe(second)
        assert presence.connected(TABLE) == frozenset()

    def test_each_table_keeps_its_own_connections(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))

        assert presence.connected(OTHER_TABLE) == frozenset()

    def test_unsubscribing_twice_changes_nothing(self, presence, wakes):
        subscription = presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        presence.unsubscribe(subscription)
        presence.unsubscribe(subscription)

        assert presence.connected(TABLE) == {"ben"}


class TestPublishing:
    def test_a_member_connecting_wakes_every_other_stream_of_the_table_but_not_its_own(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 1, "ben": 0}

    def test_a_member_leaving_wakes_the_others(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        leaving = presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        presence.unsubscribe(leaving)

        assert wakes.counts == {"anna": 2, "ben": 0}

    def test_a_second_tab_of_a_connected_account_changes_nobodys_view_and_wakes_nobody(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        first = presence.subscribe(TABLE, "ben", wakes.callback("ben"))
        before = dict(wakes.counts)

        second = presence.subscribe(TABLE, "ben", wakes.callback("ben-again"))
        presence.unsubscribe(second)

        assert wakes.counts == {**before, "ben-again": 0}
        presence.unsubscribe(first)
        assert wakes.counts["anna"] == before["anna"] + 1

    def test_another_tables_streams_hear_nothing(self, presence, wakes):
        presence.subscribe(OTHER_TABLE, "anna", wakes.callback("anna"))

        presence.subscribe(TABLE, "ben", wakes.callback("ben"))

        assert wakes.counts == {"anna": 0, "ben": 0}

    def test_a_stalled_stream_does_not_delay_the_others_who_hear_every_change(self, presence, wakes):
        presence.subscribe(TABLE, "stalled", wakes.callback("stalled"))
        presence.subscribe(TABLE, "quick", wakes.callback("quick"))
        joined = [presence.subscribe(TABLE, f"member-{n}", wakes.callback(f"member-{n}")) for n in range(5)]
        for subscription in joined:
            presence.unsubscribe(subscription)

        assert wakes.counts["quick"] == 10


class TestRegistrationBeforeRead:
    def test_a_change_between_registering_and_reading_is_in_the_view_the_stream_reads(self, presence, wakes):
        numbers = itertools.count(1)
        service = TableService(FakeTableStore(), new_table_id=lambda: TableId(f"{next(numbers):032x}"))
        opener = Actor(account_id="opener", display_name="Anna")
        table_id = service.create(opener, CreateTable(command_id="command-1")).id
        visitor = Actor(account_id="visitor", display_name="Ben")

        presence.subscribe(table_id, visitor.account_id, wakes.callback("visitor"))
        presence.subscribe(table_id, "late", wakes.callback("late"))
        view = service.view(visitor, table_id, presence.connected(table_id))

        assert (view.version, view.watchers) == (1, 2)
        assert wakes.counts["visitor"] == 1
