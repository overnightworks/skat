from abc import ABC, abstractmethod
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
from skat.web.tables import actor_of
from skat.web.wakes import AccountTopic, TableTopic

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from webauth.ports import SessionRecordStore

    from skat.table.lobby import LobbyEntryView
    from skat.table.records import Actor, TableId
    from skat.table.service import TableService
    from skat.web.presence import Presence
    from skat.web.wakes import Registration, WakeList

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


class LobbyTableAnswer(BaseModel):
    id: str
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


def _table_answer_of(entry: LobbyEntryView) -> LobbyTableAnswer:
    return LobbyTableAnswer(
        id=entry.id,
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
            )
            for chair in entry.chairs
        ],
    )


class AccountTablesSource(ABC):
    """The tables one account holds a chair at as a stream source, woken by its account and by those tables.

    It is no presence: nothing here connects the account to a table. Every read swaps the registration for one that
    holds the account's topic and the topics of the tables the index lists, on the event loop's thread and with no
    await between registering the new and dropping the old, so no topic is ever unheld. The tables' records are read
    after the swap, so a commit before it is in the read and a commit after it wakes the stream. A table named as
    `apart_from` is neither read nor held, so a change there never wakes the source.
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
        self._tables = tables
        self._presence = presence
        self._wakes = wakes
        self._account_id = account_id
        self._days = days
        self._apart_from = apart_from
        self._wake: Callable[[], None] | None = None
        self._registration: Registration | None = None

    async def open(self, wake: Callable[[], None]) -> None:  # NOSONAR(S7503) StreamSource.open is async
        self._wake = wake
        self._registration = self._wakes.register([AccountTopic(self._account_id)], wake)

    async def read(self, actor: Actor) -> SourceMessage:
        listed = await run_in_threadpool(self._tables.tables_held_by, actor.account_id)
        held = tuple(table_id for table_id in listed if table_id.value != self._apart_from)
        self._hold_topics_of(held)
        connected = {table_id.value: self._presence.connected(table_id.value) for table_id in held}
        entries = await run_in_threadpool(self._tables.my_tables, actor.account_id, held, connected, self._days)
        return self._message_of(entries)

    def close(self) -> None:
        assert self._registration is not None  # noqa: S101 - narrows the type; the loop closes only an opened source
        self._wakes.unregister(self._registration)

    @abstractmethod
    def _message_of(self, entries: tuple[LobbyEntryView, ...]) -> SourceMessage: ...

    def _hold_topics_of(self, held: tuple[TableId, ...]) -> None:
        assert self._wake is not None  # noqa: S101 - narrows the type; the loop reads only an opened source
        assert self._registration is not None  # noqa: S101 - narrows the type; the loop reads only an opened source
        topics = [AccountTopic(self._account_id), *(TableTopic(table_id.value) for table_id in held)]
        previous, self._registration = self._registration, self._wakes.register(topics, self._wake)
        self._wakes.unregister(previous)


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
        source = LobbySource(tables, presence, wakes, actor_of(request).account_id, paused_table_days)
        admit = session_admission(request, sessions)

        async def messages() -> AsyncIterator[str]:
            async for item in stream_messages(
                [source], admit, lambda: presence.stopped, heartbeat_seconds=heartbeat_seconds
            ):
                yield message_of(item)

        return event_stream_response(messages())

    return router
