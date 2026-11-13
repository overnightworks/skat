from abc import abstractmethod
from datetime import datetime  # noqa: TC003 - pydantic reads the field type at runtime
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from skat.table.awaiting import WaitingCase  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.records import OccupantKind  # noqa: TC001 - pydantic reads the field type at runtime
from skat.web.mcp import Exclusion, excluded
from skat.web.streams import (
    SourceMessage,
    StreamEvent,
    event_stream_response,
    message_of,
    session_admission,
    stream_messages,
)
from skat.web.table_options import OptionsAnswer, options_answer_of
from skat.web.tables import actor_of
from skat.web.wakes import AccountTopic, OpenTablesTopic, TableTopic

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterable

    from webauth.ports import SessionRecordStore

    from skat.table.lobby import LobbyEntryView, OpenEntryView
    from skat.table.records import Actor
    from skat.table.service import TableService
    from skat.web.presence import Presence
    from skat.web.wakes import Registration, Topic, WakeList

LOBBY_EVENTS_PATH: Final = "/api/lobby/events"


class LobbyChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    occupant_kind: OccupantKind | None
    is_mine: bool
    ready: bool
    total: int | None
    is_away: bool
    is_turn: bool
    hold_seconds_left: int | None


class LobbyTableAnswer(BaseModel):
    id: str
    private: bool
    title_name: str | None
    game_number: int | None
    game_count: int | None
    dealt: bool
    awaits_you: bool
    waits_on: WaitingCase | None
    result_waits: bool
    series_over: bool
    ends_at: datetime | None
    chairs: list[LobbyChairAnswer]


class MineAnswer(BaseModel):
    tables: list[LobbyTableAnswer]


class OpenChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    occupant_kind: OccupantKind | None
    is_away: bool
    hold_seconds_left: int | None


class OpenTableAnswer(BaseModel):
    id: str
    title_name: str | None
    game_number: int | None
    game_count: int | None
    options: OptionsAnswer
    watchers: int
    free_chairs: int
    dealt: bool
    waiting_seat: int | None
    ends_at: datetime | None
    chairs: list[OpenChairAnswer]


class OpenAnswer(BaseModel):
    tables: list[OpenTableAnswer]


def _table_answer_of(entry: LobbyEntryView) -> LobbyTableAnswer:
    return LobbyTableAnswer(
        id=entry.id,
        private=entry.private,
        title_name=entry.title_name,
        game_number=entry.game_number,
        game_count=entry.game_count,
        dealt=entry.dealt,
        awaits_you=entry.awaits_you,
        waits_on=entry.waits_on,
        result_waits=entry.result_waits,
        series_over=entry.series_over,
        ends_at=entry.ends_at,
        chairs=[
            LobbyChairAnswer(
                seat=chair.seat,
                occupant_name=chair.occupant_name,
                occupant_kind=chair.occupant_kind,
                is_mine=chair.is_mine,
                ready=chair.ready,
                total=chair.total,
                is_away=chair.is_away,
                is_turn=chair.is_turn,
                hold_seconds_left=chair.hold_seconds_left,
            )
            for chair in entry.chairs
        ],
    )


def _open_answer_of(entry: OpenEntryView) -> OpenTableAnswer:
    return OpenTableAnswer(
        id=entry.id,
        title_name=entry.title_name,
        game_number=entry.game_number,
        game_count=entry.game_count,
        options=options_answer_of(entry.options),
        watchers=entry.watchers,
        free_chairs=entry.free_chairs,
        dealt=entry.dealt,
        waiting_seat=entry.waiting_seat,
        ends_at=entry.ends_at,
        chairs=[
            OpenChairAnswer(
                seat=chair.seat,
                occupant_name=chair.occupant_name,
                occupant_kind=chair.occupant_kind,
                is_away=chair.is_away,
                hold_seconds_left=chair.hold_seconds_left,
            )
            for chair in entry.chairs
        ],
    )


class _TopicHoldingSource:
    """A source of tables woken by one account's topic and the topics of the tables it lists.

    Every read swaps the registration for one that holds the topics it names, on the event loop's thread and with no
    await between registering the new and dropping the old, so no topic is ever unheld. The tables' records are read
    after the swap, so a commit before it is in the read and a commit after it wakes the stream.
    """

    def __init__(self, wakes: WakeList, account_id: str) -> None:
        self._wakes = wakes
        self._account_id = account_id
        self._wake: Callable[[], None] | None = None
        self._registration: Registration | None = None

    async def open(self, wake: Callable[[], None]) -> None:  # NOSONAR(S7503) StreamSource.open is async
        self._wake = wake
        self._registration = self._wakes.register([AccountTopic(self._account_id)], wake)

    def close(self) -> None:
        assert self._registration is not None  # noqa: S101 - narrows the type; the loop closes only an opened source
        self._wakes.unregister(self._registration)

    def _hold_topics(self, topics: Iterable[Topic]) -> None:
        assert self._wake is not None  # noqa: S101 - narrows the type; the loop reads only an opened source
        assert self._registration is not None  # noqa: S101 - narrows the type; the loop reads only an opened source
        previous, self._registration = (
            self._registration,
            self._wakes.register([AccountTopic(self._account_id), *topics], self._wake),
        )
        self._wakes.unregister(previous)


class AccountTablesSource(_TopicHoldingSource):
    """The tables one account holds a chair at as a stream source, woken by its account and by those tables.

    It is no presence: nothing here connects the account to a table. A table named as `apart_from` is neither read
    nor held, so a change there never wakes the source. A table that ended, or a chair the account left, drops out of
    the next swap.
    """

    def __init__(
        self,
        tables: TableService,
        presence: Presence,
        wakes: WakeList,
        account_id: str,
        days: int,
        apart_from: str | None = None,
    ) -> None:
        super().__init__(wakes, account_id)
        self._tables = tables
        self._presence = presence
        self._days = days
        self._apart_from = apart_from

    async def read(self, actor: Actor) -> SourceMessage:
        listed = await run_in_threadpool(self._tables.tables_held_by, actor.account_id)
        held = tuple(table_id for table_id in listed if table_id.value != self._apart_from)
        self._hold_topics(TableTopic(table_id.value) for table_id in held)
        connected = {table_id.value: self._presence.connected(table_id.value) for table_id in held}
        holds = self._presence.hold_seconds_left(connected)
        entries = await run_in_threadpool(self._tables.my_tables, actor.account_id, held, connected, holds, self._days)
        return self._message_of(entries)

    @abstractmethod
    def _message_of(self, entries: tuple[LobbyEntryView, ...]) -> SourceMessage: ...  # pragma: no cover - abstract


class OpenTablesSource(_TopicHoldingSource):
    """The open tables the account holds no chair at, whole, as the event `open`.

    It holds the topic of the open tables, which a table opened wakes, and the topics of the tables it lists, so a
    sit, a stand-up, an absence, a watcher and an end at one of them reach it. Taking a chair wakes the account's topic,
    which moves the table to the account's own list.
    """

    def __init__(self, tables: TableService, presence: Presence, wakes: WakeList, account_id: str, days: int) -> None:
        super().__init__(wakes, account_id)
        self._tables = tables
        self._presence = presence
        self._days = days

    async def read(self, actor: Actor) -> SourceMessage:
        listed = await run_in_threadpool(self._tables.open_table_ids)
        self._hold_topics([OpenTablesTopic(), *(TableTopic(table_id.value) for table_id in listed)])
        connected = {table_id.value: self._presence.connected(table_id.value) for table_id in listed}
        holds = self._presence.hold_seconds_left(connected)
        entries = await run_in_threadpool(
            self._tables.open_tables, actor.account_id, listed, connected, holds, self._days
        )
        answer = OpenAnswer(tables=[_open_answer_of(entry) for entry in entries])
        return SourceMessage(answer.model_dump_json(), event=StreamEvent.OPEN)


class LobbySource(AccountTablesSource):
    """The account's tables, whole, as the event `mine`."""

    def _message_of(self, entries: tuple[LobbyEntryView, ...]) -> SourceMessage:
        answer = MineAnswer(tables=[_table_answer_of(entry) for entry in entries])
        return SourceMessage(answer.model_dump_json(), event=StreamEvent.MINE)


class AttentionSource(AccountTablesSource):
    """How many of the account's tables apart from one wait for it, as the event `attention`: one whole number."""

    def _message_of(self, entries: tuple[LobbyEntryView, ...]) -> SourceMessage:
        return SourceMessage(str(sum(entry.awaits_you for entry in entries)), event=StreamEvent.ATTENTION)


def create_lobby_router(
    tables: TableService,
    presence: Presence,
    wakes: WakeList,
    sessions: SessionRecordStore,
    heartbeat_seconds: float,
    paused_table_days: int,
) -> APIRouter:
    router = APIRouter()

    @router.get(LOBBY_EVENTS_PATH, response_class=StreamingResponse, openapi_extra=excluded(Exclusion.LIVE_STREAM))
    async def watch_lobby(request: Request) -> StreamingResponse:
        account_id = actor_of(request).account_id
        sources = [
            LobbySource(tables, presence, wakes, account_id, paused_table_days),
            OpenTablesSource(tables, presence, wakes, account_id, paused_table_days),
        ]
        admit = session_admission(request, sessions)

        async def messages() -> AsyncIterator[str]:
            async for item in stream_messages(
                sources, admit, lambda: presence.stopped, heartbeat_seconds=heartbeat_seconds
            ):
                yield message_of(item)

        return event_stream_response(messages())

    return router
