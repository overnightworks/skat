from skat.table.records import CreateTable, SitDown, StandUp
from skat.web.lobby import AttentionSource, LobbySource
from skat.web.streams import stream_messages
from skat.web.wakes import AccountTopic, WakeList
from tests.support.fake_tables import in_memory_tables
from tests.support.idle_presence import idle_presence
from tests.web.support.streams import NO_HEARTBEAT_SECONDS, admitting

DAYS = 90


class Scene:
    """A service over an in-memory store, one wake list and the presence built on it, as the app wires them."""

    def __init__(self, service=None):
        self.service = service or in_memory_tables()
        self.wakes = WakeList()
        self.presence = idle_presence(self.wakes)
        self.opened = 0

    def open_table(self, person):
        self.opened += 1
        return self.service.create(person, CreateTable(command_id=f"open-{self.opened}")).id

    def sit(self, person, table_id, seat):
        self.service.sit(person, SitDown(f"sit-{person.account_id}-{seat}", table_id, seat), frozenset())
        self.presence.wake_table(table_id)
        self.wakes.wake(AccountTopic(person.account_id))

    def stand(self, person, table_id):
        self.service.stand(person, StandUp(f"stand-{person.account_id}", table_id), frozenset())
        self.presence.wake_table(table_id)

    def source(self, person):
        return LobbySource(self.service, self.presence, self.wakes, person.account_id, DAYS)

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
