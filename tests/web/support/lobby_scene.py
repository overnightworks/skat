import json

from skat.table.records import Actor, CloseTable, CreateTable, SitDown, StandUp, Visibility
from skat.web.lobby import AttentionSource, LobbySource, OpenTablesSource
from skat.web.streams import SourceMessage, StreamEvent, stream_messages
from skat.web.wakes import AccountTopic, OpenTablesTopic, WakeList
from tests.support.fake_tables import in_memory_tables
from tests.support.idle_presence import idle_presence
from tests.web.support.streams import NO_HEARTBEAT_SECONDS, admitting, next_item

DAYS = 90

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")


async def next_mine(stream):
    """The tables of the next `mine`; fails on any other item."""
    item = await next_item(stream)
    assert isinstance(item, SourceMessage)
    assert item.event is StreamEvent.MINE
    return json.loads(item.data)["tables"]


async def next_open(stream):
    """The tables of the next `open`; fails on any other item."""
    item = await next_item(stream)
    assert isinstance(item, SourceMessage)
    assert item.event is StreamEvent.OPEN
    return json.loads(item.data)["tables"]


def ids_of(entries):
    return [entry["id"] for entry in entries]


class Scene:
    """A service over an in-memory store, one wake list and the presence built on it, as the app wires them."""

    def __init__(self, service=None):
        self.wakes = WakeList()
        self.presence = idle_presence(self.wakes)
        self.service = (service or in_memory_tables()).with_leases(self.presence.live_leases)
        self.opened = 0

    def open_table(self, person, visibility=Visibility.OPEN):
        """Open a table and wake what the create route wakes."""
        self.opened += 1
        table_id = self.service.create(person, CreateTable(command_id=f"open-{self.opened}", visibility=visibility)).id
        if visibility is Visibility.OPEN:
            self.wakes.wake(OpenTablesTopic())
        return table_id

    def close(self, person, table_id):
        self.service.close(person, CloseTable(f"close-{table_id}", table_id))
        self.presence.wake_table(table_id)

    def sit(self, person, table_id, seat):
        self.service.sit(person, SitDown(f"sit-{person.account_id}-{seat}", table_id, seat), frozenset())
        self.presence.wake_table(table_id)
        self.wakes.wake(AccountTopic(person.account_id))

    def stand(self, person, table_id):
        self.service.stand(person, StandUp(f"stand-{person.account_id}", table_id), frozenset())
        self.presence.wake_table(table_id)

    def source(self, person):
        return LobbySource(self.service, self.presence, self.wakes, person.account_id, DAYS)

    def open_source(self, person):
        return OpenTablesSource(self.service, self.presence, self.wakes, person.account_id, DAYS)

    def open_stream(self, person, heartbeat_seconds=NO_HEARTBEAT_SECONDS):
        return stream_messages(
            [self.open_source(person)],
            admitting(person),
            lambda: self.presence.stopped,
            heartbeat_seconds=heartbeat_seconds,
        )

    def attention_source(self, person, table_id):
        return AttentionSource(self.service, self.presence, self.wakes, person.account_id, DAYS, table_id)

    def attention_stream(self, person, table_id, heartbeat_seconds=NO_HEARTBEAT_SECONDS):
        return stream_messages(
            [self.attention_source(person, table_id)],
            admitting(person),
            lambda: self.presence.stopped,
            heartbeat_seconds=heartbeat_seconds,
        )

    def stream(self, person, admit=None, heartbeat_seconds=NO_HEARTBEAT_SECONDS):
        return stream_messages(
            [self.source(person)],
            admit or admitting(person),
            lambda: self.presence.stopped,
            heartbeat_seconds=heartbeat_seconds,
        )
