import pytest

from skat.web.presence import Presence

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


class TestWakingATable:
    def test_wakes_every_stream_of_that_table_and_no_other(self, presence, wakes):
        presence.subscribe(TABLE, "anna", wakes.callback("anna"))
        presence.subscribe(TABLE, "ben", wakes.callback("ben"))
        presence.subscribe(OTHER_TABLE, "cem", wakes.callback("cem"))
        before = dict(wakes.counts)

        presence.wake_table(TABLE)

        assert wakes.counts == {"anna": before["anna"] + 1, "ben": before["ben"] + 1, "cem": before["cem"]}

    def test_waking_a_table_nobody_watches_is_harmless(self, presence):
        presence.wake_table(TABLE)
